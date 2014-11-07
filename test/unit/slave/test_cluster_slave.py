from box.test.genty import genty, genty_dataset
import requests
import requests.models
from unittest.mock import ANY, call, MagicMock

from app.slave.cluster_slave import ClusterSlave
from app.util.exceptions import BadRequestError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterSlave(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.mock_network = self.patch('app.slave.cluster_slave.Network').return_value

    @genty_dataset(
        current_build_id_not_set=(None,),
        current_build_id_not_matching=(200,),
    )
    def test_start_working_on_subjob_called_with_incorrect_build_id_will_raise(self, slave_current_build_id):
        slave = ClusterSlave(port=15140, host='uncle.pennybags.gov')
        slave._current_build_id = slave_current_build_id
        incorrect_build_id = 300

        with self.assertRaises(BadRequestError, msg='Start subjob should raise error if incorrect build_id specified.'):
            slave.start_working_on_subjob(incorrect_build_id, 1, '~/test', ['ls'])

    @genty_dataset(
        current_build_id_not_set=(None,),
        current_build_id_not_matching=(200,),
    )
    def test_teardown_called_with_incorrect_build_id_will_raise(self, slave_current_build_id):
        slave = ClusterSlave(port=15140, host='uncle.pennybags.gov')
        slave._current_build_id = slave_current_build_id
        incorrect_build_id = 300

        with self.assertRaises(BadRequestError, msg='Teardown should raise error if incorrect build_id specified.'):
            slave.teardown_build(incorrect_build_id)

    @genty_dataset(
        responsive_master=(True,),
        unresponsive_master=(False,),
    )
    def test_disconnect_request_sent_if_and_only_if_master_is_responsive(self, is_master_responsive):
        master_url = 'uncle.pennybags.gov:15139'
        connect_api_url = 'http://{}/v1/slave'.format(master_url)
        disconnect_api_url = 'http://{}/v1/slave/1/disconnect'.format(master_url)
        if not is_master_responsive:
            self.mock_network.get.side_effect = requests.ConnectionError  # trigger an exception on get

        slave = ClusterSlave(port=15140, host='uncle.pennybags.gov')
        slave.connect_to_master(master_url)
        slave._send_master_disconnect_notification()

        # always expect a connect call, and if the master is responsive also expect a disconnect call
        expected_network_post_calls = [call(connect_api_url, ANY)]
        if is_master_responsive:
            expected_network_post_calls.append(call(disconnect_api_url))

        self.mock_network.post.assert_has_calls(expected_network_post_calls, any_order=True)
        self.assertEqual(self.mock_network.post.call_count, len(expected_network_post_calls),
                         'All POST requests should be accounted for in the test.')

    def test_signal_shutdown_process_disconnects_from_master_before_killing_executors(self):
        master_url = 'uncle.pennybags.gov:15139'
        disconnect_api_url = 'http://{}/v1/slave/1/disconnect'.format(master_url)
        mock_executor = self.patch('app.slave.cluster_slave.SubjobExecutor').return_value

        parent_mock = MagicMock()  # create a parent mock so we can assert on the order of child mock calls.
        parent_mock.attach_mock(self.mock_network, 'mock_network')
        parent_mock.attach_mock(mock_executor, 'mock_executor')

        slave = ClusterSlave(port=15140, host='thimble.pennybags.gov', num_executors=3)
        slave.connect_to_master(master_url)
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
        ClusterSlave(port=15140, host='thimble.pennybags.gov')
        self.trigger_graceful_app_shutdown()
        # This test is successful if app shutdown does not raise a SystemExit exception.
