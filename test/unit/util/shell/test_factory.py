from box.test.genty import genty, genty_dataset

from app.util.shell.factory import ShellClientFactory
from app.util.shell.local import LocalShellClient
from app.util.shell.remote import RemoteShellClient
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestShellClientFactory(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        self.mock_ShellClient = self.patch('app.util.shell.factory.ShellClient')

    @genty_dataset(
        local_shell=(LocalShellClient, True),
        remote_shell=(RemoteShellClient, False)
    )
    def test_create_returns_instance_of_expected(self, class_type, is_localhost_rval):
        self.mock_ShellClient.is_localhost.return_value = is_localhost_rval
        sc = ShellClientFactory.create(host='mordor', user='sauron')
        self.assertEqual(class_type, type(sc))