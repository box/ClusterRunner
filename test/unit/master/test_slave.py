
from app.master.slave import Slave
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSlave(BaseUnitTestCase):

    _FAKE_SLAVE_URL = 'splinter.sensei.net:43001'
    _FAKE_NUM_EXECUTORS = 10

    def setUp(self):
        super().setUp()
        self.mock_network = self.patch('app.master.slave.Network').return_value

    def test_disconnect_command_is_sent_during_teardown_when_slave_is_still_connected(self):
        slave = self._create_slave()
        slave.current_build_id = 3
        slave.is_alive = True

        slave.teardown()

        expected_teardown_url = 'http://splinter.sensei.net:43001/v1/build/3/teardown'
        self.mock_network.post.assert_called_once_with(expected_teardown_url)

    def test_disconnect_command_is_not_sent_during_teardown_when_slave_has_disconnected(self):
        slave = self._create_slave()
        slave.current_build_id = 3
        slave.is_alive = False

        slave.teardown()

        self.assertEqual(self.mock_network.post.call_count, 0,
                         'Master should not send teardown command to slave when slave has disconnected.')

    def _create_slave(self, **kwargs):
        """
        Create a slave for testing.
        :param kwargs: Any constructor parameters for the slave; if none are specified, test defaults will be used.
        :rtype: Slave
        """
        kwargs.setdefault('slave_url', self._FAKE_SLAVE_URL)
        kwargs.setdefault('num_executors', self._FAKE_NUM_EXECUTORS)
        return Slave(**kwargs)
