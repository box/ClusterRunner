import builtins
import http.client
from threading import Event
from unittest import skip
from unittest.mock import ANY, call, MagicMock, Mock, mock_open, patch

from genty import genty, genty_dataset
import requests
import requests.models

from app.project_type.project_type import SetupFailureError
from app.slave.cluster_slave import ClusterSlave, SlaveState
from app.util.exceptions import BadRequestError
from app.util.safe_thread import SafeThread
from app.util.single_use_coin import SingleUseCoin
from app.util.unhandled_exception_handler import UnhandledExceptionHandler
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterSlave(BaseUnitTestCase):

    _FAKE_MASTER_URL = 'uncle.pennybags.gov:15139'
    _FAKE_SLAVE_HOST = 'racecar.pennybags.gov'
    _FAKE_SLAVE_PORT = 15140

    def setUp(self):
        super().setUp()
        self.mock_network = self.patch('app.slave.cluster_slave.Network').return_value
        self.patch('app.util.fs.compress_directories')

    @genty_dataset(
        current_build_id_not_set=(None,),
        current_build_id_not_matching=(200,),
    )
    def test_start_working_on_subjob_called_with_incorrect_build_id_will_raise(self, slave_current_build_id):
        slave = self._create_cluster_slave()
        slave._current_build_id = slave_current_build_id
        incorrect_build_id = 300

        with self.assertRaises(BadRequestError, msg='Start subjob should raise error if incorrect build_id specified.'):
            slave.start_working_on_subjob(incorrect_build_id, 1, ['ls'])

    @genty_dataset(
        current_build_id_not_set=(None,),
        current_build_id_not_matching=(200,),
    )
    def test_teardown_called_with_incorrect_build_id_will_raise(self, slave_current_build_id):
        slave = self._create_cluster_slave()
        slave._current_build_id = slave_current_build_id
        incorrect_build_id = 300

        with self.assertRaises(BadRequestError, msg='Teardown should raise error if incorrect build_id specified.'):
            slave.teardown_build(incorrect_build_id)

    @genty_dataset(
        responsive_master=(True,),
        unresponsive_master=(False,),
    )
    def test_disconnect_request_sent_if_and_only_if_master_is_responsive(self, is_master_responsive):
        slave_creation_url = 'http://{}/v1/slave'.format(self._FAKE_MASTER_URL)
        master_connectivity_url = 'http://{}/v1'.format(self._FAKE_MASTER_URL)
        slave_info_url = 'http://{}/v1/slave/1'.format(self._FAKE_MASTER_URL)
        if not is_master_responsive:
            self.mock_network.get.side_effect = requests.ConnectionError  # an offline master raises ConnectionError

        slave = self._create_cluster_slave()
        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave._disconnect_from_master()

        # expect a connect call and a connectivity call, and if the master is responsive also expect a disconnect call
        expected_network_calls = [
            call.post(slave_creation_url, data=ANY),
            call.get(master_connectivity_url),
        ]
        if is_master_responsive:
            expected_network_calls.append(call.put_with_digest(slave_info_url, request_params=ANY,
                                                               secret=ANY, error_on_failure=ANY))

        self.mock_network.assert_has_calls(expected_network_calls, any_order=True)
        self.assertEqual(len(self.mock_network.method_calls), len(expected_network_calls),
                         'All requests should be accounted for in the test.')

    def test_signal_shutdown_process_disconnects_from_master_before_killing_executors(self):
        disconnect_api_url = 'http://{}/v1/slave/1'.format(self._FAKE_MASTER_URL)
        mock_executor = self.patch('app.slave.cluster_slave.SubjobExecutor').return_value

        parent_mock = MagicMock()  # create a parent mock so we can assert on the order of child mock calls.
        parent_mock.attach_mock(self.mock_network, 'mock_network')
        parent_mock.attach_mock(mock_executor, 'mock_executor')

        slave = self._create_cluster_slave(num_executors=3)
        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave._build_teardown_coin = SingleUseCoin()
        self.trigger_graceful_app_shutdown()

        expected_disconnect_call = call.mock_network.put_with_digest(disconnect_api_url, request_params=ANY,
                                                                     secret=ANY, error_on_failure=ANY)
        expected_kill_executor_call = call.mock_executor.kill()
        self.assertEqual(1, parent_mock.method_calls.count(expected_disconnect_call),
                         'Graceful shutdown should cause the slave to make a disconnect call to the master.')
        self.assertEqual(3, parent_mock.method_calls.count(expected_kill_executor_call),
                         'Graceful shutdown should cause the slave to kill all its executors.')
        self.assertLess(parent_mock.method_calls.index(expected_disconnect_call),
                        parent_mock.method_calls.index(expected_kill_executor_call),
                        'Graceful shutdown should disconnect from the master before killing its executors.')

    def test_shutting_down_before_connecting_to_master_does_not_raise_exception(self):
        self._create_cluster_slave()
        self.trigger_graceful_app_shutdown()
        # This test is successful if app shutdown does not raise a SystemExit exception.

    def test_shutting_down_after_running_a_build_does_not_raise_exception(self):
        self.patch('app.slave.cluster_slave.util.create_project_type')
        self.patch('app.slave.cluster_slave.open', new=mock_open(read_data=''), create=True)
        slave = self._create_cluster_slave()
        expected_results_api_url = 'http://{}/v1/build/123/subjob/321/result'.format(self._FAKE_MASTER_URL)
        expected_idle_api_url = 'http://{}/v1/slave/1'.format(self._FAKE_MASTER_URL)
        subjob_done_event, teardown_done_event, setup_done_event = self._mock_network_post_and_put(expected_results_api_url,
                                                                                 expected_idle_api_url)
        slave.connect_to_master(self._FAKE_MASTER_URL)

        slave.setup_build(build_id=123, project_type_params={'type': 'Fake'}, build_executor_start_index=0)
        self.assertTrue(setup_done_event.wait(timeout=5), 'Setup code under test should put to expected idle '
                                                          'url very quickly.')

        slave.start_working_on_subjob(build_id=123, subjob_id=321, atomic_commands=[])
        # The timeout for this wait() is arbitrary, but it should be generous so the test isn't flaky on slow machines.
        self.assertTrue(subjob_done_event.wait(timeout=5), 'Subjob execution code under test should post to expected '
                                                           'results url very quickly.')

        slave.teardown_build(123)
        self.assertTrue(teardown_done_event.wait(timeout=5), 'Teardown code under test should put to expected idle '
                                                             'url very quickly.')
        self.trigger_graceful_app_shutdown()  # Triggering shutdown should not raise an exception.

    def _mock_network_post_and_put(self, expected_results_api_url, expected_idle_api_url):
        # Since subjob execution and teardown is async, we use Events to tell our test when each thread has completed.
        subjob_done_event = Event()
        setup_done_event = Event()
        teardown_done_event = Event()

        def _get_success_mock_response():
            mock_response = MagicMock(spec=requests.models.Response, create=True)
            mock_response.status_code = http.client.OK
            return mock_response

        def fake_network_post(url, *args, **kwargs):
            if url == expected_results_api_url:
                subjob_done_event.set()  # Consider subjob finished once code posts to results url.
            return _get_success_mock_response()

        def fake_network_put(url, request_params, **kwargs):
            if url == expected_idle_api_url:
                if request_params['slave']['state'] == SlaveState.SETUP_COMPLETED:
                    setup_done_event.set()
                elif request_params['slave']['state'] == SlaveState.IDLE:
                    teardown_done_event.set()
            return _get_success_mock_response()

        self.mock_network.post = fake_network_post
        self.mock_network.put = fake_network_put
        self.mock_network.put_with_digest = fake_network_put
        return subjob_done_event, teardown_done_event, setup_done_event

    @skip('Flaky - see issue # 178')
    def test_executing_build_teardown_multiple_times_will_not_raise_exception(self):
        self.mock_network.post().status_code = http.client.OK
        slave = self._create_cluster_slave()
        project_type_mock = self.patch('app.slave.cluster_slave.util.create_project_type').return_value
        # This test uses setup_complete_event to detect when the async fetch_project() has executed.
        setup_complete_event = Event()
        project_type_mock.fetch_project.side_effect = self.no_args_side_effect(setup_complete_event.set)
        # This test uses teardown_event to cause a thread to block on the teardown_build() call.
        teardown_event = Event()
        project_type_mock.teardown_build = Mock()

        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave.setup_build(build_id=123, project_type_params={'type': 'Fake'}, build_executor_start_index=0)
        self.assertTrue(setup_complete_event.wait(timeout=5), 'Build setup should complete very quickly.')

        # Start the first thread that does build teardown. This thread will block on teardown_build().
        first_thread = SafeThread(target=slave._do_build_teardown_and_reset)
        first_thread.start()
        # Call build teardown() again and it should not run teardown again
        slave._do_build_teardown_and_reset()

        project_type_mock.teardown_build.assert_called_once_with(timeout=None)
        # Cleanup: Unblock the first thread and let it finish. We use the unhandled exception handler just in case any
        # exceptions occurred on the thread (so that they'd be passed back to the main thread and fail the test).
        teardown_event.set()
        with UnhandledExceptionHandler.singleton():
            first_thread.join()

    @genty_dataset(
        successful_setup=(True, SlaveState.SETUP_COMPLETED),
        failed_setup=(False, SlaveState.SETUP_FAILED),
    )
    def test_setup_should_send_correct_state_update_to_master(self, is_setup_successful, expected_slave_state):
        expected_slave_data_url = 'http://{}/v1/slave/1'.format(self._FAKE_MASTER_URL)
        slave = self._create_cluster_slave()
        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave._project_type = MagicMock()
        if not is_setup_successful:
            slave._project_type.fetch_project.side_effect = SetupFailureError

        slave._async_setup_build(executors=[], project_type_params={}, build_executor_start_index=0)

        self.mock_network.put_with_digest.assert_called_once_with(
            expected_slave_data_url, request_params={'slave': {'state': expected_slave_state}},
            secret=ANY, error_on_failure=True)

    def test_async_setup_happy_path_invokes_correct_methods(self):
        slave = self._create_cluster_slave()
        slave.connect_to_master(self._FAKE_MASTER_URL)
        project_type_mock = self.patch('app.slave.cluster_slave.util.create_project_type').return_value
        slave._project_type = project_type_mock
        slave._async_setup_build([], {}, 0)

        project_type_mock.fetch_project.assert_called_once_with()
        self.assertTrue(project_type_mock.run_job_config_setup.called)

    def test_setup_build_sets_base_executor_index(self):
        slave = self._create_cluster_slave()
        slave.setup_build(build_id=123, project_type_params={'type': 'Fake'}, build_executor_start_index=8)
        self.assertEqual(8, slave._base_executor_index, 'Build setup should set _base_executor_index')

    def test_execute_subjob_passes_base_executor_index_to_executor(self):
        slave = self._create_cluster_slave()
        slave._base_executor_index = 12
        slave._master_api = Mock()
        executor = Mock()
        slave._idle_executors = Mock()

        with patch.object(builtins, 'open', mock_open(read_data='asdf')):
            slave._execute_subjob(build_id=1, subjob_id=2, executor=executor, atomic_commands=[])

        executor.execute_subjob.assert_called_with(1, 2, [], 12)

    def _create_cluster_slave(self, **kwargs):
        """
        Create a ClusterSlave for testing.
        :param kwargs: Any constructor parameters for the slave; if none are specified, test defaults will be used.
        :rtype: ClusterSlave
        """
        kwargs.setdefault('host', self._FAKE_SLAVE_HOST)
        kwargs.setdefault('port', self._FAKE_SLAVE_PORT)
        return ClusterSlave(**kwargs)
