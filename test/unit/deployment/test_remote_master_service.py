from unittest.mock import Mock

from app.deployment.remote_master_service import RemoteMasterService
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestRemoteMasterService(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        self.patch('time.sleep')

    def test_start_and_block_until_up_raises_exception_if_process_fails_to_start(self):
        self._mock_shell_exec_command({
            'nohup some_path master --port 43000 &': "\n",
            'ps ax | grep \'[s]ome_path\'': "\n",
        })
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        with self.assertRaisesRegex(SystemExit, '1'):
            remote_master_service.start_and_block_until_up(43000, 5)

    def test_start_and_block_until_up_raises_exception_if_process_starts_by_service_doesnt_respond(self):
        self._mock_shell_exec_command({
            'nohup some_path master --port 43000 &': "\n",
            'ps ax | grep \'[s]ome_path\'': "\nsome_path\n",
        })
        self.patch('app.deployment.remote_master_service.ServiceRunner').return_value.is_up.return_value = False
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        with self.assertRaisesRegex(SystemExit, '1'):
            remote_master_service.start_and_block_until_up(43000, 5)

    def test_start_and_block_until_up_doesnt_raise_exception_if_master_service_is_up(self):
        self._mock_shell_exec_command({
            'nohup some_path master --port 43000 &': "\n",
            'ps ax | grep \'[s]ome_path\'': "\nsome_path\n",
        })
        self.patch('app.deployment.remote_master_service.ServiceRunner').return_value.is_up.return_value = True
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        remote_master_service.start_and_block_until_up(43000, 5)

    def test_is_process_running_returns_false_if_only_empty_output(self):
        self._mock_shell_exec_command({'ps ax | grep \'[s]ome_command\'': "\n"})
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        self.assertFalse(remote_master_service._is_process_running('some_command'))

    def test_is_process_running_returns_true_if_found_non_empty_output(self):
        self._mock_shell_exec_command({'ps ax | grep \'[s]ome_command\'': "\nrealoutput\n"})
        remote_master_service = RemoteMasterService('some_host', 'some_username', 'some_path')
        self.assertTrue(remote_master_service._is_process_running('some_command'))

    def _mock_shell_exec_command(self, command_response_dict):
        """
        :param command_response_dict: a dictionary with the key being the expected input, and the value being the
            raw output that will be returned.
        :type command_response_dict: dict[str, str]
        """
        def exec_command(*args, **kwargs):
            nonlocal command_response_dict
            if args[0] in command_response_dict:
                response_mock = Mock()
                response_mock.raw_output = command_response_dict[args[0]].encode('utf-8')
                response_mock.raw_error = None
                response_mock.returncode = 0
                return response_mock

        shell_client_mock = self.patch('app.util.shell.remote_shell_client.RemoteShellClient').return_value
        shell_client_mock.exec_command.side_effect = exec_command
        self.patch('app.deployment.remote_service.ShellClientFactory').create.return_value = shell_client_mock