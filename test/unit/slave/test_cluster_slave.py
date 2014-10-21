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
        slave_connect_api_url = 'http://uncle.pennybags.gov:15139/v1/slave'
        slave_disconnect_api_url = 'http://uncle.pennybags.gov:15139/v1/slave/1/disconnect'
        if not is_master_responsive:
            self.mock_network.get.side_effect = requests.ConnectionError  # trigger an exception on get

        slave = ClusterSlave(port=15140, host='uncle.pennybags.gov')
        slave.connect_to_master(master_url)
        slave._async_teardown_build(should_disconnect_from_master=True)

        # always expect a connect call, and if the master is responsive also expect a disconnect call
        expected_network_post_calls = [call(slave_connect_api_url, ANY)]
        if is_master_responsive:
            expected_network_post_calls.append(call(slave_disconnect_api_url))

        self.mock_network.post.assert_has_calls(expected_network_post_calls, any_order=True)
        self.assertEqual(self.mock_network.post.call_count, len(expected_network_post_calls),
                         'All POST requests should be accounted for in the test.')
