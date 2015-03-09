import psutil
import signal
from unittest.mock import mock_open, Mock

from app.subcommands.stop_subcommand import StopSubcommand
from test.framework.base_unit_test_case import BaseUnitTestCase

NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL = 4

class TestStopSubcommand(BaseUnitTestCase):


    def setUp(self):
        super().setUp()
        self.patch('os.remove')
        self.os_kill_patch = self.patch('os.kill')
        self.patch('time.sleep')
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

    def setup_environment_for_os_kill(self, main_proc_pid):
        self.os_path_exists_patch.return_value = True
        self._mock_open(read_data=str(main_proc_pid))
        self.psutil_pid_exists_patch.side_effect = [True, False, False]
        self.mock_time_so_while_loop_ran_once()

    def mock_time_so_while_loop_ran_once(self):
        mock_time = self.patch('app.subcommands.stop_subcommand.time')
        start_time = 0
        mock_time.time.side_effect = [
            start_time,
            start_time + StopSubcommand.SIGTERM_SIGKILL_GRACE_PERIOD_SEC - 1,
            start_time + StopSubcommand.SIGTERM_SIGKILL_GRACE_PERIOD_SEC + 1]

    def setup_main_and_child_proc(self, main_proc_pid, main_is_running_threshold, child_pid,
                                  child_is_running_threshold):
        self.patch('psutil.Process').return_value = self.create_process_mock(
            pid=main_proc_pid,
            is_running_threshold=main_is_running_threshold,
            cmdline=['python', './main.py', 'master'],
            children=[
                self.create_process_mock(pid=child_pid, is_running_threshold=child_is_running_threshold)
            ]
        )

    def create_process_mock(self, pid, is_running_threshold=None, cmdline=None, children=None):
        m = Mock(spec_set=psutil.Process)
        m.pid = pid
        is_running_threshold = is_running_threshold if is_running_threshold else 0
        m.is_running.side_effect = [True] * is_running_threshold + [False] * 10000
        if cmdline:
            m.cmdline.return_value = cmdline

        m.children.return_value = children if children else []
        return m

    def test_stop_subcommand_kills_pid_with_sigterm_if_pid_file_and_pid_exist_and_command_is_whitelisted(self):
        main_proc_pid = 9999
        threshold = NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL - 1
        child_pid = main_proc_pid + 1

        self.setup_environment_for_os_kill(main_proc_pid)
        self.setup_main_and_child_proc(main_proc_pid, threshold, child_pid, threshold)

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.os_kill_patch.assert_called_with(main_proc_pid, signal.SIGTERM)
        self.assertEquals(2, self.os_kill_patch.call_count)

    def test_stop_subcommand_kills_main_proc_with_sigkill_if_still_running_after_sigterm(self):
        main_proc_pid = 9999
        child_proc_pid = main_proc_pid + 1
        main_threshold = NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL
        child_threshold = NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL - 1

        self.setup_environment_for_os_kill(main_proc_pid)
        self.setup_main_and_child_proc(main_proc_pid,main_threshold, child_proc_pid, child_threshold)

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.os_kill_patch.assert_called_with(main_proc_pid, signal.SIGKILL)
        self.assertEquals(3, self.os_kill_patch.call_count)

    def test_stop_subcommand_kills_child_proc_with_sigkill_if_still_running_after_sigterm(self):
        main_proc_pid = 9999
        main_threshold = NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL - 1
        child_threshold = NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL
        child_pid = main_proc_pid + 1

        self.setup_environment_for_os_kill(main_proc_pid)
        self.setup_main_and_child_proc(main_proc_pid, main_threshold, child_pid, child_threshold)

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.os_kill_patch.assert_called_with(child_pid, signal.SIGKILL)
        self.assertEquals(3, self.os_kill_patch.call_count)

    def test_stop_subcommand_kills_proc_with_sigterm(self):
        main_proc_pid = 9999

        self.setup_environment_for_os_kill(main_proc_pid)
        self.patch('psutil.Process').return_value = self.create_process_mock(
            pid=main_proc_pid,
            is_running_threshold=NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL - 1,
            cmdline=['python', './main.py', 'master'],
            children=[]
        )

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.os_kill_patch.assert_called_with(main_proc_pid, signal.SIGTERM)
        self.assertEquals(1, self.os_kill_patch.call_count)

    def test_stop_subcommand_kills_proc_with_sigkill(self):
        main_proc_pid = 9999

        self.setup_environment_for_os_kill(main_proc_pid)
        self.patch('psutil.Process').return_value = self.create_process_mock(
            pid=main_proc_pid,
            is_running_threshold=NUM_OF_IS_RUNNING_CHECKS_TILL_SIGKILL,
            cmdline=['python', './main.py', 'master'],
            children=[]
        )

        stop_subcommand = StopSubcommand()
        stop_subcommand._kill_pid_in_file_if_exists('/tmp/pid_file_path.pid')

        self.os_kill_patch.assert_called_with(main_proc_pid, signal.SIGKILL)
        self.assertEquals(2, self.os_kill_patch.call_count)
