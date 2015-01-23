from genty import genty, genty_dataset

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.shell.shell_client import ShellClient


@genty
class TestShellClient(BaseUnitTestCase):

    _HOST = 'host'
    _USER = 'user'

    @genty_dataset(
        async_and_err_on_failure=(NotImplementedError, True, True)
    )
    def test_exec_command_raises_expected_error(self, expected_error, async, error_on_failure):
        client = ShellClient(self._HOST, self._USER)
        with self.assertRaises(expected_error):
            client.exec_command('foo', async=async, error_on_failure=error_on_failure)
