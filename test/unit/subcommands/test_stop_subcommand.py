from functools import partial
from io import StringIO
import os
from os.path import join
from unittest.mock import call, mock_open, Mock

import psutil

from app.subcommands.stop_subcommand import Configuration, StopSubcommand
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestStopSubcommand(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self._mock_os_path_exists = self.patch('os.path.exists')
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

    def _setup_pid_file_does_not_exist(self):
        self._mock_os_path_exists.return_value = False

    def _setup_pid_file_exists_but_pid_does_not_exist(self):
        self._mock_os_path_exists.return_value = True
        self._mock_psutil_pid_exists.return_value = False

    def _setup_both_pid_file_and_pids_exist(self):
        self._mock_os_path_exists.return_value = True
        self._mock_psutil_pid_exists.return_value = True

    def test_stop_subcommand_does_not_call_terminate_if_pid_file_does_not_exist(self):
        # Arrange
        self._setup_pid_file_does_not_exist()

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertFalse(self._mock_psutil_process.terminate.called)
        self.assertEqual(
            [
                call(self._fake_slave_pid_file_sys_path),
                call(self._fake_master_pid_file_sys_path),
            ],
            self._mock_os_path_exists.call_args_list,
        )

    def test_stop_subcommand_does_not_call_terminate_if_pid_does_not_exist(self):
        # Arrange
        self._setup_pid_file_exists_but_pid_does_not_exist()

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertFalse(self._mock_psutil_process.terminate.called)
        self.assertEqual(
            [
                call(self._fake_slave_pid_file_sys_path),
                call(self._fake_master_pid_file_sys_path),
            ],
            self._mock_os_remove.call_args_list,
        )

    def test_stop_subcommand_does_not_call_terminate_if_pid_file_and_pid_exist_but_command_isnt_whitelisted(self):
        # Arrange
        self._setup_both_pid_file_and_pids_exist()
        self._setup_processes(
            master_cmdline=['python', './foo.py'],
            slave_cmdline=['python', './bar.py'],
        )

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self.assertFalse(self._mock_psutil_process.terminate.called)

    def _create_mock_process(self, pid, child_processes=None, cmdline=None):
        proc = Mock(psutil.Process)
        proc.pid = pid
        proc.is_running.return_value = True
        if cmdline:
            proc.cmdline.return_value = cmdline
        proc.children.return_value = child_processes if child_processes else []
        return proc

    def _setup_processes(self, master_cmdline=None, slave_cmdline=None):
        master_process = self._create_mock_process(
            self._fake_master_pid,
            cmdline=master_cmdline if master_cmdline else ['python', 'main.py', 'master'],
        )

        slave_child_process = self._create_mock_process(3333)
        slave_process = self._create_mock_process(
            self._fake_slave_pid,
            child_processes=[slave_child_process],
            cmdline=slave_cmdline if slave_cmdline else ['python', 'main.py', 'slave'],
        )

        self._mock_psutil_process.side_effect = [
            slave_process,
            master_process,
        ]

        return master_process, slave_process, slave_child_process

    def _assert_called_terminate(self, process_list):
        for proc in process_list:
            self.assertTrue(proc.terminate.called)

    @staticmethod
    def _successful_terminate_or_kill(proc):
        proc.is_running.return_value = False

    def test_stop_subcommand_kills_pid_with_sigterm_if_pid_file_and_pid_exist_and_command_is_whitelisted(self):
        # Arrange
        self._setup_both_pid_file_and_pids_exist()
        master_process, slave_process, slave_child_process = self._setup_processes()

        master_process.terminate.side_effect = partial(self._successful_terminate_or_kill, master_process)
        slave_process.terminate.side_effect = partial(self._successful_terminate_or_kill, slave_process)
        slave_child_process.terminate.side_effect = partial(self._successful_terminate_or_kill, slave_child_process)

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self._assert_called_terminate([master_process, slave_process, slave_child_process])
        self.assertFalse(master_process.kill.called)
        self.assertFalse(slave_process.kill.called)
        self.assertFalse(slave_child_process.kill.called)

    def test_stop_subcommand_kills_proc_with_sigkill_if_still_running_after_sigterm(self):
        # Arrange
        self._setup_both_pid_file_and_pids_exist()
        master_process, slave_process, slave_child_process = self._setup_processes()
        master_process.terminate.side_effect = partial(self._successful_terminate_or_kill, master_process)

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self._assert_called_terminate([master_process, slave_process, slave_child_process])
        self.assertFalse(master_process.kill.called)
        self.assertTrue(slave_process.kill.called)
        self.assertTrue(slave_child_process.kill.called)
