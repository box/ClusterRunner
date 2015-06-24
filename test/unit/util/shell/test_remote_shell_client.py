from genty import genty, genty_dataset

from app.util.shell.remote_shell_client import RemoteShellClient
from app.util.shell.shell_client import Response, EmptyResponse
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestRemoteShellClient(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        self.mock_Popen = self.patch('app.util.shell.remote_shell_client.Popen_with_delayed_expansion')

    @genty_dataset(
        normal_response=(False, Response(raw_output=b'\ncat', raw_error=b'\ndog', returncode=0)),
        async_response=(True, EmptyResponse())
    )
    def test_exec_command_returns_expected(self, async_enabled, response):
        self.mock_popen_communicate_call(stdout=b'\ncat', stderr=b'\ndog')
        client = RemoteShellClient('host', 'user')
        res = client.exec_command('ls', async=async_enabled)
        self.assertEqual(res, response)

    def mock_popen_communicate_call(self, stdout=b'\n', stderr=b'', returncode=0):
        mock_popen = self.mock_Popen.return_value
        mock_popen.communicate.return_value = stdout, stderr
        mock_popen.returncode = returncode
