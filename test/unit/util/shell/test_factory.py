from genty import genty, genty_dataset

from app.util.shell.shell_client_factory import ShellClientFactory
from app.util.shell.local_shell_client import LocalShellClient
from app.util.shell.remote_shell_client import RemoteShellClient
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestShellClientFactory(BaseUnitTestCase):
    @genty_dataset(
        local_shell=(LocalShellClient, 'localhost'),
        remote_shell=(RemoteShellClient, 'mordor')
    )
    def test_create_returns_instance_of_expected(self, expected_class_type, host_name):
        shell_client = ShellClientFactory.create(host=host_name, user='sauron')
        self.assertEqual(expected_class_type, type(shell_client))
