from genty import genty, genty_dataset

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.shell.local_shell_client import LocalShellClient
from app.util.shell.shell_client import Response, EmptyResponse


@genty
class TestLocalShellClient(BaseUnitTestCase):

    _HOST = 'host'
    _USER = 'user'
    _SOURCE = 'source'
    _DESTINATION = 'destination'

    def setUp(self):
        super().setUp()
        self.mock_shutil = self.patch('app.util.shell.local_shell_client.shutil')
        self.mock_Popen = self.patch('app.util.shell.local_shell_client.Popen_with_delayed_expansion')

    @genty_dataset(
        empty_response=(True, EmptyResponse()),
        normal_response=(False, Response())
    )
    def test_exec_command_returns_expected_response(self, async, expected):
        self.create_mock_popen()
        client = LocalShellClient(self._HOST, self._USER)
        res = client.exec_command('ls', async=async)
        self.assertEqual(res, expected)

    def create_mock_popen(self, output=None, error=None, retcode=None):
        mock_popen = self.mock_Popen.return_value
        mock_popen.returncode = retcode
        mock_popen.communicate.return_value = output, error
        return mock_popen

    def test_copy_returns_expected_response(self):
        expected = Response(raw_output=self._DESTINATION.encode(), returncode=0)
        self.mock_shutil_copy_rval(self._DESTINATION)
        client = LocalShellClient(self._HOST, self._USER)
        res = client.copy(self._SOURCE, self._DESTINATION)
        self.assertEqual(res, expected)

    def mock_shutil_copy_rval(self, new_rval):
        self.mock_shutil.copy.return_value = new_rval
