from box.test.genty import genty, genty_dataset
import http.client
import requests
import requests.models
from threading import Event
from unittest.mock import ANY, call, MagicMock, mock_open

from app.slave.cluster_slave import ClusterSlave, BuildTeardownError
from app.util.exceptions import BadRequestError
from app.util.safe_thread import SafeThread
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
            slave.start_working_on_subjob(incorrect_build_id, 1, '~/test', ['ls'])

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
        connect_api_url = 'http://{}/v1/slave'.format(self._FAKE_MASTER_URL)
        disconnect_api_url = 'http://{}/v1/slave/1/disconnect'.format(self._FAKE_MASTER_URL)
        if not is_master_responsive:
            self.mock_network.get.side_effect = requests.ConnectionError  # trigger an exception on get

        slave = self._create_cluster_slave()
        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave._send_master_disconnect_notification()

        # always expect a connect call, and if the master is responsive also expect a disconnect call
        expected_network_post_calls = [call(connect_api_url, ANY)]
        if is_master_responsive:
            expected_network_post_calls.append(call(disconnect_api_url))

        self.mock_network.post.assert_has_calls(expected_network_post_calls, any_order=True)
        self.assertEqual(self.mock_network.post.call_count, len(expected_network_post_calls),
                         'All POST requests should be accounted for in the test.')

    def test_signal_shutdown_process_disconnects_from_master_before_killing_executors(self):
        disconnect_api_url = 'http://{}/v1/slave/1/disconnect'.format(self._FAKE_MASTER_URL)
        mock_executor = self.patch('app.slave.cluster_slave.SubjobExecutor').return_value

        parent_mock = MagicMock()  # create a parent mock so we can assert on the order of child mock calls.
        parent_mock.attach_mock(self.mock_network, 'mock_network')
        parent_mock.attach_mock(mock_executor, 'mock_executor')

        slave = self._create_cluster_slave(num_executors=3)
        slave.connect_to_master(self._FAKE_MASTER_URL)
        self.trigger_graceful_app_shutdown()

        expected_disconnect_call = call.mock_network.post(disconnect_api_url)
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
        expected_idle_api_url = 'http://{}/v1/slave/1/idle'.format(self._FAKE_MASTER_URL)
        subjob_done_event, teardown_done_event = self._mock_network_post(expected_results_api_url,
                                                                         expected_idle_api_url)
        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave.setup_build(build_id=123, project_type_params={'type': 'Fake'})
        slave.start_working_on_subjob(build_id=123, subjob_id=321,
                                      subjob_artifact_dir='', atomic_commands=[])
        # The timeout for this wait() is arbitrary, but it should be generous so the test isn't flaky on slow machines.
        self.assertTrue(subjob_done_event.wait(timeout=5), 'Subjob execution code under test should post to expected '
                                                           'results url very quickly.')
        slave.teardown_build(123)
        self.assertTrue(teardown_done_event.wait(timeout=5), 'Teardown code under test should post to expected idle '
                                                             'url very quickly.')
        self.trigger_graceful_app_shutdown()  # Triggering shutdown should not raise an exception.

    def _mock_network_post(self, expected_results_api_url, expected_idle_api_url):
        # Since subjob execution and teardown is async, we use Events to tell our test when each thread has completed.
        subjob_done_event = Event()
        teardown_done_event = Event()

        def fake_network_post(url, *args, **kwargs):
            if url == expected_results_api_url:
                subjob_done_event.set()  # Consider subjob finished once code posts to results url.
            elif url == expected_idle_api_url:
                teardown_done_event.set()
            mock_response = MagicMock(spec=requests.models.Response, create=True)
            mock_response.status_code = http.client.OK
            return mock_response

        self.mock_network.post = fake_network_post
        return subjob_done_event, teardown_done_event

    def test_executing_build_teardown_multiple_times_will_raise_exception(self):
        self.mock_network.post().status_code = http.client.OK
        slave = self._create_cluster_slave()
        # We use an Event here to make teardown_build() block and reliably recreate the race condition in the test.
        teardown_event = Event()
        project_type_mock = self.patch('app.slave.cluster_slave.util.create_project_type').return_value
        project_type_mock.teardown_build.side_effect = teardown_event.wait

        slave.connect_to_master(self._FAKE_MASTER_URL)
        slave.setup_build(build_id=123, project_type_params={'type': 'Fake'})
        self.assertTrue(slave._setup_complete_event.wait(timeout=5), 'Job setup should complete very quickly.')

        # Start the first thread that does build teardown. This thread will block on teardown_build().
        first_thread = SafeThread(target=slave._do_build_teardown_and_reset)
        first_thread.start()
        # Call build teardown() again and it should raise an exception.
        with self.assertRaises(BuildTeardownError):
            slave._do_build_teardown_and_reset()

        # Cleanup: unblock first thread and let it finish..
        teardown_event.set()
        with UnhandledExceptionHandler.singleton():
            first_thread.join()

    def _create_cluster_slave(self, **kwargs):
        """
        Create a ClusterSlave for testing.
        :param kwargs: Any constructor parameters for the slave; if none are specified, test defaults will be used.
        :rtype: ClusterSlave
        """
        kwargs.setdefault('host', self._FAKE_SLAVE_HOST)
        kwargs.setdefault('port', self._FAKE_SLAVE_PORT)
        return ClusterSlave(**kwargs)
