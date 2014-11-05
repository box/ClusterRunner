from box.test.genty import genty, genty_dataset
from unittest.mock import Mock

from app.util.shell.remote import RemoteShellClient
from app.util.shell.shell_client import Response, EmptyResponse
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestRemoteShellClient(BaseUnitTestCase):
    _HOST = 'host'
    _USER = 'user'
    _OUTPUT = '\noutput\nfrom\nparamiko\nis\na\nnonsplit\nstring'
    _ERROR = '\nso\nare\nerrors'

    def setUp(self):
        super().setUp()
        self.mock_socket = self.patch('app.util.shell.shell_client.socket')
        self.mock_Popen = self.patch('app.util.shell.local_shell_client.Popen')

    @genty_dataset(
        normal_response=(False, Response(raw_output='\ncat'.encode(), raw_error='\ndog'.encode())),
        async_response=(True, EmptyResponse())
    )
    def test_exec_command_returns_expected(self, async_enabled, response):
        mock_ssh = self.mock_SSHClient.return_value
        mock_ssh.exec_command.return_value = self.mock_ssh_exec_command_rvals(
            out_contents='\ncat',
            err_contents='\ndog'
        )
        client = RemoteShellClient(self._HOST, self._USER)
        client.connect()
        res = client.exec_command('ls', async=async_enabled)
        self.assertTrue(res.compare_to(response))

    def mock_ssh_exec_command_rvals(self, out_contents=None, err_contents=None, returncode=None):
        stdin, stdout, stderr = None, Mock(), Mock()
        stdout.readlines.return_value = out_contents or self._OUTPUT
        stdout.channel.recv_exit_status.return_value = returncode
        stderr.readlines.return_value = err_contents or self._ERROR
        return stdin, stdout, stderr
