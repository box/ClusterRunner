from app.deployment.remote_master_service import RemoteMasterService
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestRemoteMasterService(BaseUnitTestCase):
    def test_start_and_block_until_up_raises_exception_if_master_service_not_up(self):
        self.patch('app.deployment.remote_service.ShellClientFactory')
        self.patch('app.deployment.remote_master_service.ServiceRunner').return_value.is_up.return_value = False
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        with self.assertRaisesRegex(SystemExit, '1'):
            remote_master_service.start_and_block_until_up(43000, 5)

    def test_start_and_block_until_up_doesnt_raise_exception_if_master_service_is_up(self):
        self.patch('app.deployment.remote_service.ShellClientFactory')
        self.patch('app.deployment.remote_master_service.ServiceRunner').return_value.is_up.return_value = True
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        remote_master_service.start_and_block_until_up(43000, 5)