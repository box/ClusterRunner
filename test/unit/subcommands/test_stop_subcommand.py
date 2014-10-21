import signal
from unittest.mock import mock_open

from app.subcommands.stop_subcommand import StopSubcommand
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestStopSubcommand(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('os.remove')
        self.patch('time.sleep')
        self.os_kill_patch = self.patch('os.kill')
        self.os_path_exists_patch = self.patch('os.path.exists')
        self.psutil_pid_exists_patch = self.patch('psutil.pid_exists')

    def _mock_open(self, read_data):
        open_mock = mock_open(read_data=read_data)
        self.patch('app.subcommands.stop_subcommand.open', new=open_mock, create=True)

    def test_stop_subcommand_doesnt_kill_pid_if_pid_file_doesnt_exist(self):
        self.os_path_exists_patch.return_value = False

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.assertFalse(self.os_kill_patch.called)

    def test_stop_subcommand_doesnt_kill_pid_if_pid_file_exists_but_pid_doesnt_exist(self):
        self.os_path_exists_patch.return_value = True
        self.psutil_pid_exists_patch.side_effect = [False]
        self._mock_open(read_data='9999')

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.assertFalse(self.os_kill_patch.called)

    def test_stop_subcommand_doesnt_kill_pid_if_pid_file_and_pid_exist_but_command_isnt_whitelisted(self):
        self.os_path_exists_patch.return_value = True
        self.psutil_pid_exists_patch.side_effect = [True]
        self._mock_open(read_data='9999')
        mock_psutil_process = self.patch('psutil.Process').return_value
        mock_psutil_process.cmdline.return_value = ['python', './SOME_OTHER_main.py', 'other_master']

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.assertFalse(self.os_kill_patch.called)

    def test_stop_subcommand_kills_pid_with_sigterm_if_pid_file_and_pid_exist_and_command_is_whitelisted(self):
        self.os_path_exists_patch.return_value = True
        self._mock_open(read_data='9999')
        self.psutil_pid_exists_patch.side_effect = [True, False, False]
        mock_psutil_process = self.patch('psutil.Process').return_value
        mock_psutil_process.cmdline.return_value = ['python', './main.py', 'master']

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.os_kill_patch.assert_called_with(9999, signal.SIGTERM)
