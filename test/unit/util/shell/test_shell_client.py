from genty import genty, genty_dataset, genty_args

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.shell.shell_client import ShellClient, Response


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

    @genty_dataset(
        successful_copy_with_error_on_failure=genty_args(
            source='source0',
            dest='dest0',
            error_on_failure=True,
            copy_successful=True,
            expect_runtime_error=False,
        ),
        failed_copy_with_error_on_failure=genty_args(
            source='source1',
            dest='dest1',
            error_on_failure=True,
            copy_successful=False,
            expect_runtime_error=True,
        ),
        failed_copy_without_error_on_failure=genty_args(
            source='source2',
            dest='dest2',
            error_on_failure=False,
            copy_successful=False,
            expect_runtime_error=False,
        ),
        successful_copy_without_error_on_failure=genty_args(
            source='source3',
            dest='dest3',
            error_on_failure=False,
            copy_successful=True,
            expect_runtime_error=False,
        ),
    )
    def test_copy(self, source, dest, error_on_failure, copy_successful, expect_runtime_error):
        # Arrange
        client = ShellClient(self._HOST, self._USER)
        mock_copy_on_client = self.patch('app.util.shell.shell_client.ShellClient._copy_on_client')
        res = Response(returncode=0 if copy_successful else 1)
        mock_copy_on_client.return_value = res

        # Act
        if expect_runtime_error:
            with self.assertRaises(RuntimeError):
                client.copy(source, dest, error_on_failure)
        else:
            self.assertEqual(client.copy(source, dest, error_on_failure), res)

        # Assert
        mock_copy_on_client.assert_called_once_with(client, source, dest)
