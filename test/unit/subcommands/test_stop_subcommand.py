from io import StringIO
import os
from os.path import join
import signal
from unittest.mock import call, mock_open, Mock

import psutil

from app.subcommands.stop_subcommand import Configuration, StopSubcommand
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestStopSubcommand(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self._mock_os_path_exists = self.patch('os.path.exists')
        self._mock_os_kill = self.patch('os.kill')
        self._mock_psutil_pid_exists = self.patch('psutil.pid_exists')
        self._mock_psutil_process = self.patch('psutil.Process')

        self._fake_slave_pid_file_sys_path = join(os.getcwd(), 'slave_pid_file')
        self._fake_master_pid_file_sys_path = join(os.getcwd(), 'master_pid_file')
        Configuration['slave_pid_file'] = self._fake_slave_pid_file_sys_path
        Configuration['master_pid_file'] = self._fake_master_pid_file_sys_path

        self._fake_slave_pid = 1111
        self._fake_master_pid = 2222
        self._mock_open = mock_open()
        self._mock_open.side_effect = [
            StringIO(str(self._fake_slave_pid)),     # pretend to be fhe slave pid file object
            StringIO(str(self._fake_master_pid)),    # pretend to be the master pid file object
        ]

        self.patch('app.subcommands.stop_subcommand.open', new=self._mock_open, create=True)
        self._mock_os_remove = self.patch('os.remove')

        self._stop_subcommand = StopSubcommand()

        # setup the return value of time.time() and SIGTERM grace period so the test won't actually sleep
        self._stop_subcommand.SIGTERM_SIGKILL_GRACE_PERIOD_SEC = -1
        mock_time = self.patch('time.time')
        mock_time.return_value = 0

    def test_stop_subcommand_does_not_kill_if_pid_file_does_not_exist(self):
        # Arrange
        self._mock_os_path_exists.return_value = False

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertFalse(self._mock_os_kill.called)
        self.assertEqual(
            [
                call(self._fake_slave_pid_file_sys_path),
                call(self._fake_master_pid_file_sys_path),
            ],
            self._mock_os_path_exists.call_args_list,
        )

    def test_stop_subcommand_does_not_kill_pid_if_pid_does_not_exist(self):
        # Arrange
        self._mock_os_path_exists.return_value = True
        self._mock_psutil_pid_exists.return_value = False

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertFalse(self._mock_os_kill.called)
        self.assertEqual(
            [
                call(self._fake_slave_pid_file_sys_path),
                call(self._fake_master_pid_file_sys_path),
            ],
            self._mock_os_remove.call_args_list,
        )

    def test_stop_subcommand_doesnt_kill_pid_if_pid_file_and_pid_exist_but_command_isnt_whitelisted(self):
        # Arrange
        self._mock_os_path_exists.return_value = True
        self._mock_psutil_pid_exists.return_value = True
        master_process = Mock(psutil.Process)
        master_process.cmdline.return_value = ['python', './foo.py']
        slave_process = Mock(psutil.Process)
        slave_process.cmdline.return_value = ['python', './bar.py']
        self._mock_psutil_process.side_effect = [
            slave_process,
            master_process,
        ]

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertFalse(self._mock_os_kill.called)

    def _create_mock_process(self, pid, child_processes=None, cmdline=None):
        proc = Mock(psutil.Process)
        proc.pid = pid
        proc.is_running.return_value = True
        if cmdline:
            proc.cmdline.return_value = cmdline
        proc.children.return_value = child_processes if child_processes else []
        return proc

    def _setup_processes_to_be_killed(self):
        self._mock_os_path_exists.return_value = True
        self._mock_psutil_pid_exists.return_value = True

        master_process = self._create_mock_process(
            self._fake_master_pid,
            cmdline=['python', 'main.py', 'master'],
        )

        slave_child_process = self._create_mock_process(3333)
        slave_process = self._create_mock_process(
            self._fake_slave_pid,
            child_processes=[slave_child_process],
            cmdline=['python', 'main.py', 'slave'],
        )

        self._mock_psutil_process.side_effect = [
            slave_process,
            master_process,
        ]


        return master_process, slave_process, slave_child_process

    def test_stop_subcommand_kills_pid_with_sigterm_if_pid_file_and_pid_exist_and_command_is_whitelisted(self):
        # Arrange
        master_process, slave_process, slave_child_process = self._setup_processes_to_be_killed()

        def terminate_processes_successfully(pid, _):
            if pid == self._fake_master_pid:
                master_process.is_running.return_value = False
            elif pid == self._fake_slave_pid:
                slave_process.is_running.return_value = False
            else:
                slave_child_process.is_running.return_value = False
        self._mock_os_kill.side_effect = terminate_processes_successfully

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertEqual(
            [
                call(slave_child_process.pid, signal.SIGTERM),
                call(slave_process.pid, signal.SIGTERM),
                call(master_process.pid, signal.SIGTERM),
            ],
            self._mock_os_kill.call_args_list,
        )

    def test_stop_subcommand_kills_proc_with_sigkill_if_still_running_after_sigterm(self):
        # Arrange
        master_process, slave_process, slave_child_process = self._setup_processes_to_be_killed()

        def terminate_only_master_process_successfully(pid, _):
            if pid == self._fake_master_pid:
                master_process.is_running.return_value = False

        self._mock_os_kill.side_effect = terminate_only_master_process_successfully

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertEqual(
            [
                call(slave_child_process.pid, signal.SIGTERM),
                call(slave_process.pid, signal.SIGTERM),
                call(slave_child_process.pid, signal.SIGKILL),
                call(slave_process.pid, signal.SIGKILL),
                call(master_process.pid, signal.SIGTERM),
            ],
            self._mock_os_kill.call_args_list,
        )
