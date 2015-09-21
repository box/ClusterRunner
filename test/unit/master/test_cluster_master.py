from genty import genty, genty_dataset
from hypothesis import given
from hypothesis.strategies import text, dictionaries, integers
from unittest.mock import MagicMock, Mock

from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.slave.cluster_slave import SlaveState
from app.util.exceptions import BadRequestError, ItemNotFoundError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterMaster(BaseUnitTestCase):
    # todo: This test class leaks threads. Every time we instantiate a ClusterMaster object we start up two threads
    # todo: that will live for the rest of the nosetests run. We should 1) enable ClusterMaster to shut down the
    # todo: threads that it starts and 2) make tests fail that leak threads.

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')
        self.patch('os.makedirs')
        self.mock_slave_allocator = self.patch('app.master.cluster_master.SlaveAllocator').return_value
        self.mock_scheduler_pool = self.patch('app.master.cluster_master.BuildSchedulerPool').return_value

    @genty_dataset(
        slave_id_specified=({'slave_id': 400},),
        slave_url_specified=({'slave_url': 'michelangelo.turtles.gov'},),
    )
    def test_get_slave_raises_exception_on_slave_not_found(self, get_slave_kwargs):
        master = ClusterMaster()
        master.connect_slave('raphael.turtles.gov', 10)
        master.connect_slave('leonardo.turtles.gov', 10)
        master.connect_slave('donatello.turtles.gov', 10)

        with self.assertRaises(ItemNotFoundError):
            master.get_slave(**get_slave_kwargs)

    @genty_dataset(
        both_arguments_specified=({'slave_id': 1, 'slave_url': 'raphael.turtles.gov'},),
        neither_argument_specified=({},),
    )
    def test_get_slave_raises_exception_on_invalid_arguments(self, get_slave_kwargs):
        master = ClusterMaster()
        master.connect_slave('raphael.turtles.gov', 10)

        with self.assertRaises(ValueError):
            master.get_slave(**get_slave_kwargs)

    def test_get_slave_returns_expected_value_given_valid_arguments(self):
        master = ClusterMaster()
        master.connect_slave('raphael.turtles.gov', 10)
        master.connect_slave('leonardo.turtles.gov', 10)
        master.connect_slave('donatello.turtles.gov', 10)

        actual_slave_by_id = master.get_slave(slave_id=2)
        actual_slave_by_url = master.get_slave(slave_url='leonardo.turtles.gov')

        self.assertEqual(2, actual_slave_by_id.id, 'Retrieved slave should have the same id as requested.')
        self.assertEqual('leonardo.turtles.gov', actual_slave_by_url.url,
                         'Retrieved slave should have the same url as requested.')

    def test_connect_slave_adds_new_slave_if_slave_never_connected_before(self):
        master = ClusterMaster()

        master.connect_slave('never-before-seen.turtles.gov', 10)

        self.assertEqual(1, len(master.all_slaves_by_id()), 'Exactly one slave should be registered with the master.')
        self.assertIsNotNone(master.get_slave(slave_id=None, slave_url='never-before-seen.turtles.gov'),
                             'Registered slave does not have the expected url.')

    def test_connect_slave_with_existing_dead_slave_creates_new_alive_instance(self):
        master = ClusterMaster()
        master.connect_slave('existing-slave.turtles.gov', 10)
        existing_slave = master.get_slave(slave_id=None, slave_url='existing-slave.turtles.gov')
        existing_slave.set_is_alive(False)
        existing_slave_id = existing_slave.id

        connect_response = master.connect_slave('existing-slave.turtles.gov', 10)
        new_slave = master._all_slaves_by_url.get('existing-slave.turtles.gov')

        self.assertNotEqual(str(existing_slave_id), connect_response['slave_id'],
                            'The re-connected slave should have generated a new slave id.')
        self.assertTrue(new_slave.is_alive(use_cached=True),
                        'The new slave should have been marked as alive once instantiated.')
        self.assertEquals(2, self.mock_slave_allocator.add_idle_slave.call_count,
                          'Expected slave to be added to the idle slaves list.')

    def test_connect_slave_with_existing_slave_running_build_cancels_build(self):
        master = ClusterMaster()
        master.connect_slave('running-slave.turtles.gov', 10)
        build_mock = MagicMock(spec_set=Build)
        master._all_builds_by_id[1] = build_mock
        existing_slave = master.get_slave(slave_id=None, slave_url='running-slave.turtles.gov')
        existing_slave.current_build_id = 1

        master.connect_slave('running-slave.turtles.gov', 10)

        self.assertTrue(build_mock.cancel.called, 'The build was not cancelled.')

    def test_update_build_with_valid_params_succeeds(self):
        build_id = 1
        update_params = {'key': 'value'}
        master = ClusterMaster()
        build = Mock()
        master._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        success, response = master.handle_request_to_update_build(build_id, update_params)

        build.update_state.assert_called_once_with(update_params)
        self.assertTrue(success, "Update build should return success")
        self.assertEqual(response, {}, "Response should be empty")

    def test_update_build_with_bad_build_id_fails(self):
        build_id = 1
        invalid_build_id = 2
        update_params = {'key': 'value'}
        master = ClusterMaster()
        build = Mock()
        master._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        with self.assertRaises(ItemNotFoundError):
            master.handle_request_to_update_build(invalid_build_id, update_params)

    def test_updating_slave_to_disconnected_state_should_mark_slave_as_dead(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, num_executors=10)
        slave = master.get_slave(slave_url=slave_url)
        self.assertTrue(slave.is_alive())

        master.handle_slave_state_update(slave, SlaveState.DISCONNECTED)

        self.assertFalse(slave.is_alive())

    def test_updating_slave_to_disconnected_state_should_reset_slave_current_build_id(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, num_executors=10)
        slave = master.get_slave(slave_url=slave_url)
        slave.current_build_id = 4

        master.handle_slave_state_update(slave, SlaveState.DISCONNECTED)

        self.assertIsNone(slave.current_build_id)

    def test_updating_slave_to_setup_completed_state_should_tell_build_to_begin_subjob_execution(self):
        master = ClusterMaster()
        fake_build = MagicMock(spec_set=Build)
        master.get_build = MagicMock(return_value=fake_build)
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)
        mock_scheduler = self.mock_scheduler_pool.get(fake_build)

        master.handle_slave_state_update(slave, SlaveState.SETUP_COMPLETED)

        mock_scheduler.begin_subjob_executions_on_slave.assert_called_once_with(slave)

    def test_updating_slave_to_shutdown_should_call_slave_set_shutdown_mode(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)
        slave.set_shutdown_mode = Mock()

        master.handle_slave_state_update(slave, SlaveState.SHUTDOWN)

        slave.set_shutdown_mode.assert_called_once_with()

    def test_updating_slave_to_nonexistent_state_should_raise_bad_request_error(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)

        with self.assertRaises(BadRequestError):
            master.handle_slave_state_update(slave, 'NONEXISTENT_STATE')

    def test_handle_result_reported_from_slave_does_nothing_when_build_is_canceled(self):
        build_id = 1
        slave_url = "url"
        build = Build(BuildRequest({}))
        build.cancel()
        self.patch_object(build, '_handle_subjob_payload')
        self.patch_object(build, '_mark_subjob_complete')

        master = ClusterMaster()
        master._all_builds_by_id[build_id] = build
        master._all_slaves_by_url[slave_url] = Mock()
        mock_scheduler = self.mock_scheduler_pool.get(build)

        master.handle_result_reported_from_slave(slave_url, build_id, 1)

        self.assertEqual(build._handle_subjob_payload.call_count, 0, "Build is canceled, should not handle payload")
        self.assertEqual(build._mark_subjob_complete.call_count, 0, "Build is canceled, should not complete subjobs")
        self.assertEqual(mock_scheduler.execute_next_subjob_or_free_executor.call_count, 0,
                         "Build is canceled, should not do next subjob")

    def test_exception_raised_during_complete_subjob_does_not_prevent_slave_teardown(self):
        slave_url = 'raphael.turtles.gov'
        mock_build = Mock(spec_set=Build, build_id=lambda: 777, is_finished=False)
        mock_build.complete_subjob.side_effect = [RuntimeError('Write failed')]

        master = ClusterMaster()
        master._all_builds_by_id[mock_build.build_id()] = mock_build
        master._all_slaves_by_url[slave_url] = Mock()
        mock_scheduler = self.mock_scheduler_pool.get(mock_build)

        with self.assertRaisesRegex(RuntimeError, 'Write failed'):
            master.handle_result_reported_from_slave(slave_url, mock_build.build_id(), subjob_id=888)

        self.assertEqual(mock_scheduler.execute_next_subjob_or_free_executor.call_count, 1)

    @given(dictionaries(text(), text()))
    def test_handle_request_for_new_build_does_not_raise_exception(self, build_params):
        master = ClusterMaster()
        master.handle_request_for_new_build(build_params)

    @given(integers(), dictionaries(text(), text()))
    def test_handle_request_to_update_build_does_not_raise_exception(self, build_id, update_params):
        master = ClusterMaster()
        master._all_builds_by_id = {build_id: Build({})}
        master.handle_request_to_update_build(build_id, update_params)
