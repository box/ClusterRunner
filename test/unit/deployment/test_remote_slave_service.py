import socket
from unittest.mock import Mock

from genty import genty, genty_dataset

from app.deployment.remote_slave_service import RemoteSlaveService
from app.util.shell.shell_client import ShellClient
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestRemoteSlaveService(BaseUnitTestCase):

    _HOST_NAME = socket.gethostname()

    def _patch_shell_client_factory(self):
        mock_shell_client_factory = self.patch('app.deployment.remote_service.ShellClientFactory')
        mock_shell_client = Mock(ShellClient)
        mock_shell_client_factory.create.return_value = mock_shell_client
        return mock_shell_client

    @genty_dataset(
        connect_to_master_host=('host1', 'username1', '/path/to/exec1', 'master_host', 43000, 43001, 10),
        connect_to_localhost=('host2', 'username2', '/path/to/exec2', 'localhost', 123, 321, 30),
    )
    def test_start(self, host, username, executable_path, master_host, master_port, slave_port, num_executors):
        # Arrange
        mock_shell_client = self._patch_shell_client_factory()

        # Act
        remote_slave_service = RemoteSlaveService(host, username, executable_path)
        remote_slave_service.start(master_host, master_port, slave_port, num_executors)

        # Assert
        mock_shell_client.exec_command.assert_called_once_with(
            'nohup {} slave --master-url {}:{} --port {} --num-executors {} &'.format(
                executable_path,
                master_host if master_host != 'localhost' else self._HOST_NAME,
                master_port,
                slave_port,
                num_executors,
            ),
            async=True,
        )
