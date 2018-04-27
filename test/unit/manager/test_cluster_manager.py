from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from typing import Optional

from genty import genty, genty_dataset
from hypothesis import given
from hypothesis.strategies import text, dictionaries, integers
from unittest.mock import MagicMock, Mock

from app.manager.atom import Atom
from app.manager.build import Build
from app.manager.build_request import BuildRequest
from app.manager.build_store import BuildStore
from app.manager.cluster_manager import ClusterManager
from app.manager.worker import Worker, WorkerRegistry
from app.manager.subjob import Subjob
from app.worker.cluster_worker import WorkerState
from app.util.conf.configuration import Configuration
from app.util.exceptions import BadRequestError, ItemNotFoundError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterManager(BaseUnitTestCase):
    _PAGINATION_OFFSET = 0
    _PAGINATION_LIMIT = 5
    _PAGINATION_MAX_LIMIT = 10
    _NUM_BUILDS = _NUM_SUBJOBS = _NUM_ATOMS = 20

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')
        self.patch('os.makedirs')
        self.mock_worker_allocator = self.patch('app.manager.cluster_manager.WorkerAllocator').return_value
        self.mock_scheduler_pool = self.patch('app.manager.cluster_manager.BuildSchedulerPool').return_value

        # mock datetime class inside cluster manager
        self._mock_current_datetime = datetime(2018,4,1)
        self._mock_datetime = self.patch('app.manager.cluster_manager.datetime')
        self._mock_datetime.now.return_value = self._mock_current_datetime

        # Two threads are ran everytime we start up the ClusterManager. We redirect the calls to
        # `ThreadPoolExecutor.submit` through a mock proxy so we can capture events.
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=2)
        self._thread_pool_executor_cls = self.patch('app.manager.cluster_manager.ThreadPoolExecutor')
        self._thread_pool_executor_cls.return_value.submit.side_effect = \
            self.thread_pool_executor.submit

        WorkerRegistry.reset_singleton()

        Configuration['pagination_offset'] = self._PAGINATION_OFFSET
        Configuration['pagination_limit'] = self._PAGINATION_LIMIT
        Configuration['pagination_max_limit'] = self._PAGINATION_MAX_LIMIT

    def tearDown(self):
        super().tearDown()
        self.thread_pool_executor.shutdown()

    def test_connect_worker_adds_new_worker_if_worker_never_connected_before(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()

        manager.connect_worker('never-before-seen.turtles.gov', 10)

        self.assertEqual(1, len(worker_registry.get_all_workers_by_id()),
                         'Exactly one worker should be registered with the manager.')
        self.assertIsNotNone(worker_registry.get_worker(worker_id=None, worker_url='never-before-seen.turtles.gov'),
                             'Registered worker does not have the expected url.')

    def test_connect_worker_with_existing_dead_worker_creates_new_alive_instance(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()

        manager.connect_worker('existing-worker.turtles.gov', 10)
        existing_worker = worker_registry.get_worker(worker_id=None, worker_url='existing-worker.turtles.gov')
        existing_worker.set_is_alive(False)
        existing_worker_id = existing_worker.id

        connect_response = manager.connect_worker('existing-worker.turtles.gov', 10)
        new_worker = worker_registry.get_worker(worker_url='existing-worker.turtles.gov')

        self.assertNotEqual(str(existing_worker_id), connect_response['worker_id'],
                            'The re-connected worker should have generated a new worker id.')
        self.assertTrue(new_worker.is_alive(use_cached=True),
                        'The new worker should have been marked as alive once instantiated.')
        self.assertEquals(2, self.mock_worker_allocator.add_idle_worker.call_count,
                          'Expected worker to be added to the idle workers list.')

    def test_connect_worker_with_existing_worker_running_build_cancels_build(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()

        manager.connect_worker('running-worker.turtles.gov', 10)
        build_mock = MagicMock(spec_set=Build)
        BuildStore._all_builds_by_id[1] = build_mock
        existing_worker = worker_registry.get_worker(worker_id=None, worker_url='running-worker.turtles.gov')
        existing_worker.current_build_id = 1

        manager.connect_worker('running-worker.turtles.gov', 10)

        self.assertTrue(build_mock.cancel.called, 'The build was not cancelled.')

    def test_update_build_with_valid_params_succeeds(self):
        build_id = 1
        update_params = {'key': 'value'}
        manager = ClusterManager()
        build = Mock()
        BuildStore._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        success, response = manager.handle_request_to_update_build(build_id, update_params)

        build.update_state.assert_called_once_with(update_params)
        self.assertTrue(success, "Update build should return success")
        self.assertEqual(response, {}, "Response should be empty")

    def test_update_build_with_bad_build_id_fails(self):
        build_id = 1
        invalid_build_id = 2
        update_params = {'key': 'value'}
        manager = ClusterManager()
        build = Mock()
        BuildStore._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        with self.assertRaises(ItemNotFoundError):
            manager.handle_request_to_update_build(invalid_build_id, update_params)

    def test_updating_worker_to_disconnected_state_should_mark_worker_as_dead(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        worker_url = 'raphael.turtles.gov'
        manager.connect_worker(worker_url, num_executors=10)
        worker = worker_registry.get_worker(worker_url=worker_url)
        self.assertTrue(worker.is_alive())

        manager.handle_worker_state_update(worker, WorkerState.DISCONNECTED)

        self.assertFalse(worker.is_alive())

    def test_updating_worker_to_disconnected_state_should_reset_worker_current_build_id(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        worker_url = 'raphael.turtles.gov'
        manager.connect_worker(worker_url, num_executors=10)
        worker = worker_registry.get_worker(worker_url=worker_url)
        worker.current_build_id = 4

        manager.handle_worker_state_update(worker, WorkerState.DISCONNECTED)

        self.assertIsNone(worker.current_build_id)

    def test_updating_worker_to_setup_completed_state_should_tell_build_to_begin_subjob_execution(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        fake_build = MagicMock(spec_set=Build)
        manager.get_build = MagicMock(return_value=fake_build)
        worker_url = 'raphael.turtles.gov'
        manager.connect_worker(worker_url, 10)
        worker = worker_registry.get_worker(worker_url=worker_url)
        mock_scheduler = self.mock_scheduler_pool.get(fake_build)
        scheduler_begin_event = Event()
        mock_scheduler.begin_subjob_executions_on_worker.side_effect = lambda **_: scheduler_begin_event.set()

        manager.handle_worker_state_update(worker, WorkerState.SETUP_COMPLETED)

        was_called = scheduler_begin_event.wait(timeout=5)
        self.assertTrue(was_called, 'scheduler.begin_subjob_executions_on_worker should be called in response '
                                    'to worker setup completing.')
        _, call_kwargs = mock_scheduler.begin_subjob_executions_on_worker.call_args
        self.assertEqual(call_kwargs.get('worker'), worker)

    def test_updating_worker_to_shutdown_should_call_worker_set_shutdown_mode(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        worker_url = 'raphael.turtles.gov'
        manager.connect_worker(worker_url, 10)
        worker = worker_registry.get_worker(worker_url=worker_url)
        worker.set_shutdown_mode = Mock()

        manager.handle_worker_state_update(worker, WorkerState.SHUTDOWN)

        worker.set_shutdown_mode.assert_called_once_with()

    def test_updating_worker_to_nonexistent_state_should_raise_bad_request_error(self):
        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        worker_url = 'raphael.turtles.gov'
        manager.connect_worker(worker_url, 10)
        worker = worker_registry.get_worker(worker_url=worker_url)

        with self.assertRaises(BadRequestError):
            manager.handle_worker_state_update(worker, 'NONEXISTENT_STATE')

    def test_update_worker_last_heartbeat_time_calls_update_last_heartbeat_time_on_worker(self):
        manager = ClusterManager()

        mock_worker = self.patch('app.manager.cluster_manager.Worker').return_value
        manager.update_worker_last_heartbeat_time(mock_worker)

        self.assertEqual(mock_worker.update_last_heartbeat_time.call_count, 1,
                         'last heartbeat time is updated for the target worker')

    @genty_dataset (
        worker_unresponsive=(True,1000,),
        worker_dead=(False,60,),
        worker_responsive=(True,60,),
    )
    def test_heartbeat_disconnects_unresponsive_worker(self, worker_alive, seconds_since_last_heartbeat):
        last_heartbeat_time = self._mock_current_datetime - timedelta(seconds=seconds_since_last_heartbeat)
        manager = ClusterManager()

        mock_worker = Mock()
        self.patch('app.manager.cluster_manager.Worker', new=lambda *args: mock_worker)
        manager.connect_worker('worker_url', 1)

        mock_worker.is_alive.return_value = worker_alive
        mock_worker.get_last_heartbeat_time.return_value = last_heartbeat_time

        manager._disconnect_non_heartbeating_workers()
        if worker_alive and seconds_since_last_heartbeat == 1000:
            self.assertEqual(mock_worker.mark_dead.call_count, 1, 'manager disconnects unresponsive worker')
        else:
            self.assertEqual(mock_worker.mark_dead.call_count, 0,
                             'manager should not disconnect a dead or responsive worker')

    def test_handle_result_reported_from_worker_when_build_is_canceled(self):
        build_id = 1
        worker_url = "url"
        build = Build(BuildRequest({}))
        self.patch('app.manager.build.util')
        build.generate_project_type()
        build.cancel()

        self.patch_object(build, '_handle_subjob_payload')
        self.patch_object(build, '_mark_subjob_complete')

        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        BuildStore._all_builds_by_id[build_id] = build
        worker_registry._all_workers_by_url[worker_url] = Mock()
        mock_scheduler = self.mock_scheduler_pool.get(build)

        manager.handle_result_reported_from_worker(worker_url, build_id, 1)

        self.assertEqual(build._handle_subjob_payload.call_count, 1, "Canceled builds should "
                                                                     "handle payload")
        self.assertEqual(build._mark_subjob_complete.call_count, 1, "Canceled builds should mark "
                                                                    "their subjobs complete")
        self.assertTrue(mock_scheduler.execute_next_subjob_or_free_executor.called)

    def test_exception_raised_during_complete_subjob_does_not_prevent_worker_teardown(self):
        worker_url = 'raphael.turtles.gov'
        mock_build = Mock(spec_set=Build, build_id=lambda: 777, is_finished=False)
        mock_build.complete_subjob.side_effect = [RuntimeError('Write failed')]

        manager = ClusterManager()
        worker_registry = WorkerRegistry.singleton()
        BuildStore._all_builds_by_id[mock_build.build_id()] = mock_build
        worker_registry._all_workers_by_url[worker_url] = Mock()
        mock_scheduler = self.mock_scheduler_pool.get(mock_build)

        with self.assertRaisesRegex(RuntimeError, 'Write failed'):
            manager.handle_result_reported_from_worker(worker_url, mock_build.build_id(), subjob_id=888)

        self.assertEqual(mock_scheduler.execute_next_subjob_or_free_executor.call_count, 1)

    @given(dictionaries(text(), text()))
    def test_handle_request_for_new_build_does_not_raise_exception(self, build_params):
        manager = ClusterManager()
        manager.handle_request_for_new_build(build_params)

    @given(integers(), dictionaries(text(), text()))
    def test_handle_request_to_update_build_does_not_raise_exception(self, build_id, update_params):
        manager = ClusterManager()
        BuildStore._all_builds_by_id = {build_id: Build({})}
        manager.handle_request_to_update_build(build_id, update_params)

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
        manager = ClusterManager()
        # Create 20 mock builds with ids 1 to 20
        for build_id in range(1, self._NUM_BUILDS + 1):
            build_mock = Mock(spec=Build)
            build_mock.build_id = build_id
            BuildStore._all_builds_by_id[build_id] = build_mock

        requested_builds = manager.get_builds(offset, limit)

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
