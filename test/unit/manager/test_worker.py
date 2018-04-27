from datetime import datetime
from genty import genty, genty_dataset
from unittest.mock import Mock, MagicMock, ANY

from app.manager.build import Build
from app.manager.build_request import BuildRequest
from app.manager.worker import DeadWorkerError, WorkerMarkedForShutdownError, Worker, WorkerError, WorkerRegistry
from app.manager.subjob import Subjob
from app.util import network
from app.util.exceptions import ItemNotFoundError
from app.util.secret import Secret
from app.util.session_id import SessionId
from test.framework.base_unit_test_case import BaseUnitTestCase
from test.framework.comparators import AnyStringMatching, AnythingOfType


class TestWorker(BaseUnitTestCase):

    _FAKE_SLAVE_URL = 'splinter.sensei.net:43001'
    _FAKE_NUM_EXECUTORS = 10

    def setUp(self):
        super().setUp()
        self.mock_network = self.patch('app.manager.worker.Network').return_value

        # mock datetime
        self._mock_current_datetime = datetime(2018,4,1)
        self._mock_datetime = self.patch('app.manager.worker.datetime')
        self._mock_datetime.now.return_value = self._mock_current_datetime

    def test_disconnect_command_is_sent_during_teardown_when_worker_is_still_connected(self):
        worker = self._create_worker()
        worker.current_build_id = 3
        worker._is_alive = True

        worker.teardown()

        expected_teardown_url = 'http://splinter.sensei.net:43001/v1/build/3/teardown'
        self.mock_network.post.assert_called_once_with(expected_teardown_url)

    def test_disconnect_command_is_not_sent_during_teardown_when_worker_has_disconnected(self):
        worker = self._create_worker()
        worker.current_build_id = 3
        worker._is_alive = False

        worker.teardown()

        self.assertEqual(self.mock_network.post.call_count, 0,
                         'Manager should not send teardown command to worker when worker has disconnected.')

    def test_git_project_params_are_modified_for_worker(self):
        worker = self._create_worker()
        worker._network.post_with_digest = Mock()

        build_request = BuildRequest({
            'type': 'git',
            'url': 'http://original-user-specified-url',
        })
        mock_git = Mock(worker_param_overrides=Mock(return_value={
            'url': 'ssh://new-url-for-clusterrunner-manager',
            'extra': 'something_extra',
        }))
        mock_build = MagicMock(spec=Build, build_request=build_request,
                               build_id=Mock(return_value=888), project_type=mock_git)

        worker.setup(mock_build, executor_start_index=777)

        worker._network.post_with_digest.assert_called_with(
            'http://{}/v1/build/888/setup'.format(self._FAKE_SLAVE_URL),
            {
                'build_executor_start_index': 777,
                'project_type_params': {
                    'type': 'git',
                    'url': 'ssh://new-url-for-clusterrunner-manager',
                    'extra': 'something_extra'}
            },
            Secret.get()
        )

    def test_build_id_is_set_on_manager_before_telling_worker_to_setup(self):
        # This test enforces an ordering that avoids a race where the worker finishes setup and posts back before the
        # manager has actually set the worker's current_build_id.
        worker = self._create_worker()
        mock_build = Mock()

        def assert_worker_build_id_is_already_set(*args, **kwargs):
            self.assertEqual(worker.current_build_id, mock_build.build_id(),
                             'worker.current_build_id should be set before the manager tells the worker to do setup.')

        worker._network.post_with_digest = Mock(side_effect=assert_worker_build_id_is_already_set)
        worker.setup(mock_build, executor_start_index=0)

        self.assertEqual(worker._network.post_with_digest.call_count, 1,
                         'The behavior that this test is checking depends on worker setup being triggered via '
                         'worker._network.post_with_digest().')

    def test_is_alive_returns_cached_value_if_use_cache_is_true(self):
        worker = self._create_worker()
        worker._is_alive = False
        is_worker_alive = worker.is_alive(use_cached=True)

        self.assertFalse(is_worker_alive)
        self.assertFalse(self.mock_network.get.called)

    def test_is_alive_returns_false_if_response_not_ok(self):
        worker = self._create_worker()
        response_mock = self.mock_network.get.return_value
        response_mock.ok = False
        is_worker_alive = worker.is_alive(use_cached=False)

        self.assertFalse(is_worker_alive)
        self.assertFalse(response_mock.json.called)

    def test_is_alive_returns_false_if_response_is_ok_but_is_alive_is_false(self):
        worker = self._create_worker()
        response_mock = self.mock_network.get.return_value
        response_mock.ok = True
        response_mock.json.return_value = {'worker': {'is_alive': False}}
        is_worker_alive = worker.is_alive(use_cached=False)

        self.assertFalse(is_worker_alive)

    def test_is_alive_returns_true_if_response_is_ok_and_is_alive_is_true(self):
        worker = self._create_worker()
        response_mock = self.mock_network.get.return_value
        response_mock.ok = True
        response_mock.json.return_value = {'worker': {'is_alive': True}}
        is_worker_alive = worker.is_alive(use_cached=False)

        self.assertTrue(is_worker_alive)

    def test_is_alive_makes_correct_network_call_to_worker(self):
        worker = self._create_worker(
            worker_url='fake.worker.gov:43001',
            worker_session_id='abc-123')

        worker.is_alive(use_cached=False)

        self.mock_network.get.assert_called_once_with(
            'http://fake.worker.gov:43001/v1',
            headers={SessionId.EXPECTED_SESSION_HEADER_KEY: 'abc-123'})

    def test_mark_as_idle_raises_when_executors_are_in_use(self):
        worker = self._create_worker()
        worker._num_executors_in_use.increment()

        self.assertRaises(Exception, worker.mark_as_idle)

    def test_mark_as_idle_raises_when_worker_is_in_shutdown_mode(self):
        worker = self._create_worker()
        worker._is_in_shutdown_mode = True

        self.assertRaises(WorkerMarkedForShutdownError, worker.mark_as_idle)
        self.mock_network.post_with_digest.assert_called_once_with(
            AnyStringMatching('/v1/kill'), ANY, ANY)

    def test_start_subjob_raises_if_worker_is_dead(self):
        worker = self._create_worker()
        worker._is_alive = False

        self.assertRaises(DeadWorkerError, worker.start_subjob, Mock())

    def test_start_subjob_raises_if_worker_is_shutdown(self):
        worker = self._create_worker()
        worker._is_in_shutdown_mode = True

        self.assertRaises(WorkerMarkedForShutdownError, worker.start_subjob, Mock())

    def test_set_shutdown_mode_should_set_is_shutdown_and_not_kill_worker_if_worker_has_a_build(self):
        worker = self._create_worker()
        worker.current_build_id = 1

        worker.set_shutdown_mode()

        self.assertTrue(worker._is_in_shutdown_mode)
        self.assertEqual(self.mock_network.post_with_digest.call_count, 0)

    def test_set_shutdown_mode_should_kill_worker_if_worker_has_no_build(self):
        worker = self._create_worker()

        worker.set_shutdown_mode()

        self.mock_network.post_with_digest.assert_called_once_with(
            AnyStringMatching('/v1/kill'), ANY, ANY)

    def test_kill_should_post_to_worker_api(self):
        worker = self._create_worker()

        worker.kill()

        self.mock_network.post_with_digest.assert_called_once_with(
            AnyStringMatching('/v1/kill'), ANY, ANY)

    def test_mark_dead_should_reset_network_session(self):
        worker = self._create_worker()

        worker.mark_dead()

        self.assertEqual(self.mock_network.reset_session.call_count, 1)

    def test_start_subjob_raises_worker_error_on_request_failure(self):
        self.mock_network.post_with_digest.side_effect = network.RequestFailedError
        worker = self._create_worker()

        with self.assertRaises(WorkerError):
            worker.start_subjob(self._create_test_subjob())

    def test_start_subjob_makes_correct_call_to_worker(self):
        worker = self._create_worker(worker_url='splinter.sensei.net:43001')
        subjob = self._create_test_subjob(build_id=911, subjob_id=187)

        worker.start_subjob(subjob)

        expected_start_subjob_url = 'http://splinter.sensei.net:43001/v1/build/911/subjob/187'
        (url, post_body, _), _ = self.mock_network.post_with_digest.call_args
        self.assertEqual(url, expected_start_subjob_url,
                         'A correct POST call should be sent to worker to start a subjob.')
        self.assertEqual(post_body, {'atomic_commands': AnythingOfType(list)},
                         'Call to start subjob should contain list of atomic_commands for this subjob.')

    def test_get_last_heartbeat_time_returns_last_heartbeat_time(self):
        worker = self._create_worker()

        self.assertEqual(worker.get_last_heartbeat_time(), self._mock_current_datetime,
                         'last heartbeat time set in the constructor')

    def test_update_last_heartbeat_time_updates_last_heartbeat_time(self):
            worker = self._create_worker()
            mock_updated_datetime = datetime(2018,4,20)
            self._mock_datetime.now.return_value = mock_updated_datetime
            worker.update_last_heartbeat_time()

            self.assertEqual(worker.get_last_heartbeat_time(), mock_updated_datetime, 'last heartbeat time is updated')

    def _create_worker(self, **kwargs) -> Worker:
        """
        Create a worker for testing.
        :param kwargs: Any constructor parameters for the worker; if none are specified, test defaults will be used.
        """
        kwargs.setdefault('worker_url', self._FAKE_SLAVE_URL)
        kwargs.setdefault('num_executors', self._FAKE_NUM_EXECUTORS)
        return Worker(**kwargs)

    def _create_test_subjob(
            self, build_id=1234, subjob_id=456, project_type=None, job_config=None, atoms=None,
    ) -> Subjob:
        """Create a subjob for testing."""
        return Subjob(
            build_id=build_id,
            subjob_id=subjob_id,
            project_type=project_type or Mock(),
            job_config=job_config or Mock(),
            atoms=atoms or [Mock()],
        )


@genty
class TestWorkerRegistry(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        WorkerRegistry.reset_singleton()

    @genty_dataset(
        worker_id_specified=({'worker_id': 400},),
        worker_url_specified=({'worker_url': 'michelangelo.turtles.gov'},),
    )
    def test_get_worker_raises_exception_on_worker_not_found(self, get_worker_kwargs):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker2 = Worker('leonardo.turtles.gov', 1)
        worker_registry.add_worker(worker1)
        worker_registry.add_worker(worker2)

        with self.assertRaises(ItemNotFoundError):
            worker_registry.get_worker(**get_worker_kwargs)

    @genty_dataset(
        both_arguments_specified=({'worker_id': 1, 'worker_url': 'raphael.turtles.gov'},),
        neither_argument_specified=({},),
    )
    def test_get_worker_raises_exception_on_invalid_arguments(self, get_worker_kwargs):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker_registry.add_worker(worker1)

        with self.assertRaises(ValueError):
            worker_registry.get_worker(**get_worker_kwargs)

    def test_get_worker_returns_valid_worker(self):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker2 = Worker('leonardo.turtles.gov', 1)
        worker_registry.add_worker(worker1)
        worker_registry.add_worker(worker2)

        self.assertEquals(worker_registry.get_worker(worker_url=worker1.url), worker1,
                          'Get worker with url should return valid worker.')
        self.assertEquals(worker_registry.get_worker(worker_id=worker2.id), worker2,
                          'Get worker with id should return valid worker.')

    def test_add_worker_adds_worker_in_both_dicts(self):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker2 = Worker('leonardo.turtles.gov', 1)
        worker_registry.add_worker(worker1)
        worker_registry.add_worker(worker2)

        self.assertEqual(2, len(worker_registry.get_all_workers_by_id()),
                         'Exactly two workers should be in the all_workers_by_id dict.')
        self.assertEqual(2, len(worker_registry.get_all_workers_by_url()),
                         'Exactly two workers should be in the all_workers_by_url dict.')

    def test_remove_worker_by_worker_instance_removes_worker_from_both_dicts(self):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker2 = Worker('leonardo.turtles.gov', 1)
        worker_registry.add_worker(worker1)
        worker_registry.add_worker(worker2)

        self.assertEqual(2, len(worker_registry.get_all_workers_by_id()),
                         'Exactly two workers should be in the all_workers_by_id dict.')
        self.assertEqual(2, len(worker_registry.get_all_workers_by_url()),
                         'Exactly two workers should be in the all_workers_by_url dict.')

        worker_registry.remove_worker(worker=worker1)

        self.assertEqual(1, len(worker_registry.get_all_workers_by_id()),
                         'Exactly one worker should be in the all_workers_by_id dict after removing one worker.')
        self.assertEqual(1, len(worker_registry.get_all_workers_by_url()),
                         'Exactly one worker should be in the all_workers_by_url dict after removing one worker.')

    def test_remove_worker_by_worker_url_removes_worker_from_both_dicts(self):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker2 = Worker('leonardo.turtles.gov', 1)
        worker_registry.add_worker(worker1)
        worker_registry.add_worker(worker2)

        self.assertEqual(2, len(worker_registry.get_all_workers_by_id()),
                         'Exactly two workers should be in the all_workers_by_id dict.')
        self.assertEqual(2, len(worker_registry.get_all_workers_by_url()),
                         'Exactly two workers should be in the all_workers_by_url dict.')

        worker_registry.remove_worker(worker_url=worker1.url)

        self.assertEqual(1, len(worker_registry.get_all_workers_by_id()),
                         'Exactly one worker should be in the all_workers_by_id dict after removing one worker.')
        self.assertEqual(1, len(worker_registry.get_all_workers_by_url()),
                         'Exactly one worker should be in the all_workers_by_url dict after removing one worker.')

    def test_remove_worker_raises_exception_on_invalid_arguments(self):
        worker_registry = WorkerRegistry.singleton()
        worker1 = Worker('raphael.turtles.gov', 1)
        worker_registry.add_worker(worker1)

        with self.assertRaises(ValueError):
            # Both arguments specified
            worker_registry.remove_worker(worker=worker1, worker_url=worker1.url)
            # No arguments specified
            worker_registry.remove_worker(worker=None, worker_url=None)
