from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from typing import Optional

from genty import genty, genty_dataset
from hypothesis import given
from hypothesis.strategies import text, dictionaries, integers
from unittest.mock import MagicMock, Mock

from app.master.atom import Atom
from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.build_store import BuildStore
from app.master.cluster_master import ClusterMaster
from app.master.slave import Slave, SlaveRegistry
from app.master.subjob import Subjob
from app.slave.cluster_slave import SlaveState
from app.util.conf.configuration import Configuration
from app.util.exceptions import BadRequestError, ItemNotFoundError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterMaster(BaseUnitTestCase):
    _PAGINATION_OFFSET = 0
    _PAGINATION_LIMIT = 5
    _PAGINATION_MAX_LIMIT = 10
    _NUM_BUILDS = _NUM_SUBJOBS = _NUM_ATOMS = 20

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')
        self.patch('os.makedirs')
        self.mock_slave_allocator = self.patch('app.master.cluster_master.SlaveAllocator').return_value
        self.mock_scheduler_pool = self.patch('app.master.cluster_master.BuildSchedulerPool').return_value

        # mock datetime class inside cluster master
        self._mock_current_datetime = datetime(2018,4,1)
        self._mock_datetime = self.patch('app.master.cluster_master.datetime')
        self._mock_datetime.now.return_value = self._mock_current_datetime

        # Two threads are ran everytime we start up the ClusterMaster. We redirect the calls to
        # `ThreadPoolExecutor.submit` through a mock proxy so we can capture events.
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=2)
        self._thread_pool_executor_cls = self.patch('app.master.cluster_master.ThreadPoolExecutor')
        self._thread_pool_executor_cls.return_value.submit.side_effect = \
            self.thread_pool_executor.submit

        SlaveRegistry.reset_singleton()

        Configuration['pagination_offset'] = self._PAGINATION_OFFSET
        Configuration['pagination_limit'] = self._PAGINATION_LIMIT
        Configuration['pagination_max_limit'] = self._PAGINATION_MAX_LIMIT

    def tearDown(self):
        super().tearDown()
        self.thread_pool_executor.shutdown()

    def test_connect_slave_adds_new_slave_if_slave_never_connected_before(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()

        master.connect_slave('never-before-seen.turtles.gov', 10)

        self.assertEqual(1, len(slave_registry.get_all_slaves_by_id()),
                         'Exactly one slave should be registered with the master.')
        self.assertIsNotNone(slave_registry.get_slave(slave_id=None, slave_url='never-before-seen.turtles.gov'),
                             'Registered slave does not have the expected url.')

    def test_connect_slave_with_existing_dead_slave_removes_old_slave_entry_from_registry(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()

        master.connect_slave('existing-slave.turtles.gov', 10)
        old_existing_slave = slave_registry.get_slave(slave_id=None, slave_url='existing-slave.turtles.gov')
        old_existing_slave_id = old_existing_slave.id

        connect_response = master.connect_slave('existing-slave.turtles.gov', 10)

        with self.assertRaises(ItemNotFoundError):
            slave_registry.get_slave(slave_id=old_existing_slave_id)

    def test_connect_slave_with_existing_dead_slave_creates_new_alive_instance(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()

        master.connect_slave('existing-slave.turtles.gov', 10)
        existing_slave = slave_registry.get_slave(slave_id=None, slave_url='existing-slave.turtles.gov')
        existing_slave.set_is_alive(False)
        existing_slave_id = existing_slave.id

        connect_response = master.connect_slave('existing-slave.turtles.gov', 10)
        new_slave = slave_registry.get_slave(slave_url='existing-slave.turtles.gov')

        self.assertNotEqual(str(existing_slave_id), connect_response['slave_id'],
                            'The re-connected slave should have generated a new slave id.')
        self.assertTrue(new_slave.is_alive(use_cached=True),
                        'The new slave should have been marked as alive once instantiated.')
        self.assertEquals(2, self.mock_slave_allocator.add_idle_slave.call_count,
                          'Expected slave to be added to the idle slaves list.')

    def test_connect_slave_with_existing_slave_running_build_cancels_build(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()

        master.connect_slave('running-slave.turtles.gov', 10)
        build_mock = MagicMock(spec_set=Build)
        BuildStore._all_builds_by_id[1] = build_mock
        existing_slave = slave_registry.get_slave(slave_id=None, slave_url='running-slave.turtles.gov')
        existing_slave.current_build_id = 1

        master.connect_slave('running-slave.turtles.gov', 10)

        self.assertTrue(build_mock.cancel.called, 'The build was not cancelled.')

    def test_update_build_with_valid_params_succeeds(self):
        build_id = 1
        update_params = {'key': 'value'}
        master = ClusterMaster()
        build = Mock()
        BuildStore._all_builds_by_id[build_id] = build
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
        BuildStore._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        with self.assertRaises(ItemNotFoundError):
            master.handle_request_to_update_build(invalid_build_id, update_params)

    def test_updating_slave_to_disconnected_state_should_mark_slave_as_dead(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, num_executors=10)
        slave = slave_registry.get_slave(slave_url=slave_url)
        self.assertTrue(slave.is_alive())

        master.handle_slave_state_update(slave, SlaveState.DISCONNECTED)

        self.assertFalse(slave.is_alive())

    def test_updating_slave_to_disconnected_state_should_reset_slave_current_build_id(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, num_executors=10)
        slave = slave_registry.get_slave(slave_url=slave_url)
        slave.current_build_id = 4

        master.handle_slave_state_update(slave, SlaveState.DISCONNECTED)

        self.assertIsNone(slave.current_build_id)

    def test_updating_slave_to_setup_completed_state_should_tell_build_to_begin_subjob_execution(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        fake_build = MagicMock(spec_set=Build)
        master.get_build = MagicMock(return_value=fake_build)
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, 10)
        slave = slave_registry.get_slave(slave_url=slave_url)
        mock_scheduler = self.mock_scheduler_pool.get(fake_build)
        scheduler_begin_event = Event()
        mock_scheduler.begin_subjob_executions_on_slave.side_effect = lambda **_: scheduler_begin_event.set()

        master.handle_slave_state_update(slave, SlaveState.SETUP_COMPLETED)

        was_called = scheduler_begin_event.wait(timeout=5)
        self.assertTrue(was_called, 'scheduler.begin_subjob_executions_on_slave should be called in response '
                                    'to slave setup completing.')
        _, call_kwargs = mock_scheduler.begin_subjob_executions_on_slave.call_args
        self.assertEqual(call_kwargs.get('slave'), slave)

    def test_updating_slave_to_shutdown_should_call_slave_set_shutdown_mode(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, 10)
        slave = slave_registry.get_slave(slave_url=slave_url)
        slave.set_shutdown_mode = Mock()

        master.handle_slave_state_update(slave, SlaveState.SHUTDOWN)

        slave.set_shutdown_mode.assert_called_once_with()

    def test_updating_slave_to_nonexistent_state_should_raise_bad_request_error(self):
        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        slave_url = 'raphael.turtles.gov'
        master.connect_slave(slave_url, 10)
        slave = slave_registry.get_slave(slave_url=slave_url)

        with self.assertRaises(BadRequestError):
            master.handle_slave_state_update(slave, 'NONEXISTENT_STATE')

    @genty_dataset (
        slave_alive=(True,1,),
        slave_dead=(False,0,),
    )
    def test_update_slave_last_heartbeat_time_calls_correspondig_slave_method(self, slave_alive, method_call_count):
        master = ClusterMaster()

        mock_slave = self.patch('app.master.cluster_master.Slave').return_value
        mock_slave.is_alive.return_value = slave_alive
        master.update_slave_last_heartbeat_time(mock_slave)

        self.assertEqual(mock_slave.update_last_heartbeat_time.call_count, method_call_count,
                         'last heartbeat time is updated for the target slave')

    @genty_dataset (
        slave_unresponsive=(True,1000,),
        slave_dead=(False,60,),
        slave_responsive=(True,60,),
    )
    def test_heartbeat_disconnects_unresponsive_slave(self, slave_alive, seconds_since_last_heartbeat):
        last_heartbeat_time = self._mock_current_datetime - timedelta(seconds=seconds_since_last_heartbeat)
        master = ClusterMaster()

        mock_slave = Mock()
        self.patch('app.master.cluster_master.Slave', new=lambda *args: mock_slave)
        master.connect_slave('slave_url', 1)

        mock_slave.is_alive.return_value = slave_alive
        mock_slave.get_last_heartbeat_time.return_value = last_heartbeat_time

        master._disconnect_non_heartbeating_slaves()
        if slave_alive and seconds_since_last_heartbeat == 1000:
            self.assertEqual(mock_slave.mark_dead.call_count, 1, 'master disconnects unresponsive slave')
        else:
            self.assertEqual(mock_slave.mark_dead.call_count, 0,
                             'master should not disconnect a dead or responsive slave')

    def test_handle_result_reported_from_slave_when_build_is_canceled(self):
        build_id = 1
        slave_url = "url"
        build = Build(BuildRequest({}))
        self.patch('app.master.build.util')
        build.generate_project_type()
        build.cancel()

        self.patch_object(build, '_handle_subjob_payload')
        self.patch_object(build, '_mark_subjob_complete')

        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        BuildStore._all_builds_by_id[build_id] = build
        slave_registry._all_slaves_by_url[slave_url] = Mock()
        mock_scheduler = self.mock_scheduler_pool.get(build)

        master.handle_result_reported_from_slave(slave_url, build_id, 1)

        self.assertEqual(build._handle_subjob_payload.call_count, 1, "Canceled builds should "
                                                                     "handle payload")
        self.assertEqual(build._mark_subjob_complete.call_count, 1, "Canceled builds should mark "
                                                                    "their subjobs complete")
        self.assertTrue(mock_scheduler.execute_next_subjob_or_free_executor.called)

    def test_exception_raised_during_complete_subjob_does_not_prevent_slave_teardown(self):
        slave_url = 'raphael.turtles.gov'
        mock_build = Mock(spec_set=Build, build_id=lambda: 777, is_finished=False)
        mock_build.complete_subjob.side_effect = [RuntimeError('Write failed')]

        master = ClusterMaster()
        slave_registry = SlaveRegistry.singleton()
        BuildStore._all_builds_by_id[mock_build.build_id()] = mock_build
        slave_registry._all_slaves_by_url[slave_url] = Mock()
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
        BuildStore._all_builds_by_id = {build_id: Build({})}
        master.handle_request_to_update_build(build_id, update_params)

    @genty_dataset(
        # No params simulates a v1 request
        no_params=(
            None, None,
            1,
            0 + _NUM_BUILDS
        ),
        # Params simulate a v2 request
        offset_param=(
            3, _PAGINATION_LIMIT,
            3 + 1,
            3 + _PAGINATION_LIMIT
        ),
        limit_param=(
            _PAGINATION_OFFSET, 5,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + 5
        ),
        offset_and_limit_params=(
            3, 5,
            3 + 1,
            3 + 5
        ),
        low_limit=(
            _PAGINATION_OFFSET, 2,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + 2
        ),
        max_limit=(
            _PAGINATION_OFFSET, _PAGINATION_MAX_LIMIT,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + _PAGINATION_MAX_LIMIT
        ),
        too_high_offset=(
            1000, _PAGINATION_LIMIT,
            None,
            None
        ),
    )
    def test_builds_with_pagination_request(
            self,
            offset: Optional[int],
            limit: Optional[int],
            expected_first_build_id: int,
            expected_last_build_id: int,
            ):
        master = ClusterMaster()
        # Create 20 mock builds with ids 1 to 20
        for build_id in range(1, self._NUM_BUILDS + 1):
            build_mock = Mock(spec=Build)
            build_mock.build_id = build_id
            BuildStore._all_builds_by_id[build_id] = build_mock

        requested_builds = master.get_builds(offset, limit)

        id_of_first_build = requested_builds[0].build_id if len(requested_builds) else None
        id_of_last_build = requested_builds[-1].build_id if len(requested_builds) else None
        num_builds = len(requested_builds)

        self.assertEqual(id_of_first_build, expected_first_build_id, 'Received the wrong first build from request')
        self.assertEqual(id_of_last_build, expected_last_build_id, 'Received the wrong last build from request')
        if offset is not None and limit is not None:
            self.assertLessEqual(num_builds, self._PAGINATION_MAX_LIMIT, 'Received too many builds from request')

    @genty_dataset(
        # No params simulates a v1 request
        no_params=(
            None, None,
            1,
            0 + _NUM_SUBJOBS
        ),
        # Params simulate a v2 request
        offset_param=(
            3, _PAGINATION_LIMIT,
            3 + 1,
            3 + _PAGINATION_LIMIT
        ),
        limit_param=(
            _PAGINATION_OFFSET, 5,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + 5
        ),
        offset_and_limit_params=(
            3, 5,
            3 + 1,
            3 + 5
        ),
        low_limit=(
            _PAGINATION_OFFSET, 2,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + 2
        ),
        max_limit=(
            _PAGINATION_OFFSET, _PAGINATION_MAX_LIMIT,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + _PAGINATION_MAX_LIMIT
        ),
        too_high_offset=(
            1000, _PAGINATION_LIMIT,
            None,
            None
        ),
    )
    def test_subjobs_with_pagination_request(
            self,
            offset: Optional[int],
            limit: Optional[int],
            expected_first_subjob_id: int,
            expected_last_subjob_id: int,
            ):
        build = Build(BuildRequest({}))
        # Create 20 mock subjobs with ids 1 to 20
        for subjob_id in range(1, self._NUM_SUBJOBS + 1):
            subjob_mock = Mock(spec=Subjob)
            subjob_mock.subjob_id = subjob_id
            build._all_subjobs_by_id[subjob_id] = subjob_mock

        requested_subjobs = build.get_subjobs(offset, limit)

        id_of_first_subjob = requested_subjobs[0].subjob_id if len(requested_subjobs) else None
        id_of_last_subjob = requested_subjobs[-1].subjob_id if len(requested_subjobs) else None
        num_subjobs = len(requested_subjobs)

        self.assertEqual(id_of_first_subjob, expected_first_subjob_id, 'Received the wrong first subjob from request')
        self.assertEqual(id_of_last_subjob, expected_last_subjob_id, 'Received the wrong last subjob from request')
        if offset is not None and limit is not None:
            self.assertLessEqual(num_subjobs, self._PAGINATION_MAX_LIMIT, 'Received too many subjobs from request')


    @genty_dataset(
        # No params simulates a v1 request
        no_params=(
            None, None,
            1,
            0 + _NUM_ATOMS
        ),
        # Params simulate a v2 request
        offset_param=(
            3, _PAGINATION_LIMIT,
            3 + 1,
            3 + _PAGINATION_LIMIT
        ),
        limit_param=(
            _PAGINATION_OFFSET, 5,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + 5
        ),
        offset_and_limit_params=(
            3, 5,
            3 + 1,
            3 + 5
        ),
        low_limit=(
            _PAGINATION_OFFSET, 2,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + 2
        ),
        max_limit=(
            _PAGINATION_OFFSET, _PAGINATION_MAX_LIMIT,
            _PAGINATION_OFFSET + 1,
            _PAGINATION_OFFSET + _PAGINATION_MAX_LIMIT
        ),
        too_high_offset=(
            1000, _PAGINATION_LIMIT,
            None,
            None
        ),
    )
    def test_atoms_with_pagination_request(
            self,
            offset: Optional[int],
            limit: Optional[int],
            expected_first_atom_id: int,
            expected_last_atom_id: int,
            ):
        # Create 20 mock atoms with ids 1 to 20
        atoms = []
        for atom_id in range(1, self._NUM_ATOMS + 1):
            atom_mock = Mock(spec=Atom)
            atom_mock.id = atom_id
            atoms.append(atom_mock)

        build_id = 1
        subjob_id = 1
        project_type = None
        job_config = None
        subjob_atoms = atoms
        subjob = Subjob(build_id, subjob_id, project_type, job_config, atoms)

        requested_atoms = subjob.get_atoms(offset, limit)

        id_of_first_atom = requested_atoms[0].id if len(requested_atoms) else None
        id_of_last_atom = requested_atoms[-1].id if len(requested_atoms) else None
        num_atoms = len(requested_atoms)

        self.assertEqual(id_of_first_atom, expected_first_atom_id, 'Received the wrong first atom from request')
        self.assertEqual(id_of_last_atom, expected_last_atom_id, 'Received the wrong last atom from request')
        if offset is not None and limit is not None:
            self.assertLessEqual(num_atoms, self._PAGINATION_MAX_LIMIT, 'Received too many atoms from request')
