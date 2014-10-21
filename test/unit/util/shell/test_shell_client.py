from box.test.genty import genty, genty_dataset

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.shell.shell_client import ShellClient


@genty
class TestShellClient(BaseUnitTestCase):

    _HOST = 'host'
    _USER = 'user'

    def setUp(self):
        super().setUp()
        self.mock_socket = self.patch('app.util.shell.shell_client.socket')

    def test_connect(self):
        client = ShellClient(self._HOST, self._USER)
        client.connect()

    def test_connecting_to_an_already_connected_instance_raises_error(self):
        client = ShellClient(self._HOST, self._USER)
        client.connect()
        with self.assertRaises(ConnectionError):
            client.connect()

    def test_close(self):
        client = ShellClient(self._HOST, self._USER)
        client.connect()
        client.close()

    def test_close_before_opening_throws_raises_error(self):
        client = ShellClient(self._HOST, self._USER)
        with self.assertRaises(ConnectionAbortedError):
            client.close()

    def test_exec_command_raises_error_when_not_connected(self):
        client = ShellClient(self._HOST, self._USER)
        with self.assertRaises(ConnectionError):
            client.exec_command('foo')

    @genty_dataset(
        async_and_err_on_failure=(NotImplementedError, True, True)
    )
    def test_exec_command_raises_expected_error(self, expected_error, async, error_on_failure):
        client = ShellClient(self._HOST, self._USER)
        client.connect()
        with self.assertRaises(expected_error):
            client.exec_command('foo', async=async, error_on_failure=error_on_failure)

    def test_copy_raises_error_when_expected(self):
        client = ShellClient(self._HOST, self._USER)
        with self.assertRaises(ConnectionError):
            client.copy('src', 'dest')

    @genty_dataset(
        on_localhost=('localhost', 'localhost', True),
        negative_test=('redfield', 'localhost', False),
        same_hostname=('redfield', 'redfield', True),
        alias_localhost=('welkers-mbp', 'localhost', True)
    )
    def test_is_localhost(self, query_hostname, local_hostname, expected):
        self.mock_gethostbyname_rvals({
            'redfield': '89.24.141.211',
            'kennedy': '173.78.183.223',
            'localhost': '127.0.0.1',
        })
        self.mock_hostname_of_local_machine(local_hostname)
        self.assertEqual(expected, ShellClient.is_localhost(query_hostname))

    def mock_gethostbyname_rvals(self, host_addr_map):
        """Maps hostname to ip addresses, and defaults to loopback address"""
        self.mock_socket.gethostbyname = lambda x: host_addr_map.get(x, '127.0.0.1')

    def mock_hostname_of_local_machine(self, host):
        self.mock_socket.gethostname.return_value = host