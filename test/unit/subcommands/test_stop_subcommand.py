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

        self._fake_worker_pid_file_sys_path = join(os.getcwd(), 'worker_pid_file')
        self._fake_manager_pid_file_sys_path = join(os.getcwd(), 'manager_pid_file')
        Configuration['worker_pid_file'] = self._fake_worker_pid_file_sys_path
        Configuration['manager_pid_file'] = self._fake_manager_pid_file_sys_path

        self._fake_worker_pid = 1111
        self._fake_manager_pid = 2222
        self._mock_open = mock_open()
        self._mock_open.side_effect = [
            StringIO(str(self._fake_worker_pid)),     # pretend to be fhe worker pid file object
            StringIO(str(self._fake_manager_pid)),    # pretend to be the manager pid file object
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
                call(self._fake_worker_pid_file_sys_path),
                call(self._fake_manager_pid_file_sys_path),
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
                call(self._fake_worker_pid_file_sys_path),
                call(self._fake_manager_pid_file_sys_path),
            ],
            self._mock_os_remove.call_args_list,
        )

    def test_stop_subcommand_does_not_call_terminate_if_pid_file_and_pid_exist_but_command_isnt_whitelisted(self):
        # Arrange
        self._setup_both_pid_file_and_pids_exist()
        self._setup_processes(
            manager_cmdline=['python', './foo.py'],
            worker_cmdline=['python', './bar.py'],
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

    def _setup_processes(self, manager_cmdline=None, worker_cmdline=None):
        manager_process = self._create_mock_process(
            self._fake_manager_pid,
            cmdline=manager_cmdline if manager_cmdline else ['python', '-m', 'app', 'manager'],
        )

        worker_child_process = self._create_mock_process(3333)
        worker_process = self._create_mock_process(
            self._fake_worker_pid,
            child_processes=[worker_child_process],
            cmdline=worker_cmdline if worker_cmdline else ['python', '-m', 'app', 'worker'],
        )

        self._mock_psutil_process.side_effect = [
            worker_process,
            manager_process,
        ]

        return manager_process, worker_process, worker_child_process

    def _assert_called_terminate(self, process_list):
        for proc in process_list:
            self.assertTrue(proc.terminate.called)

    @staticmethod
    def _successful_terminate_or_kill(proc):
        proc.is_running.return_value = False

    def test_stop_subcommand_kills_pid_with_sigterm_if_pid_file_and_pid_exist_and_command_is_whitelisted(self):
        # Arrange
        self._setup_both_pid_file_and_pids_exist()
        manager_process, worker_process, worker_child_process = self._setup_processes()

        manager_process.terminate.side_effect = partial(self._successful_terminate_or_kill, manager_process)
        worker_process.terminate.side_effect = partial(self._successful_terminate_or_kill, worker_process)
        worker_child_process.terminate.side_effect = partial(self._successful_terminate_or_kill, worker_child_process)

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self._assert_called_terminate([manager_process, worker_process, worker_child_process])
        self.assertFalse(manager_process.kill.called)
        self.assertFalse(worker_process.kill.called)
        self.assertFalse(worker_child_process.kill.called)

    def test_stop_subcommand_kills_proc_with_sigkill_if_still_running_after_sigterm(self):
        # Arrange
        self._setup_both_pid_file_and_pids_exist()
        manager_process, worker_process, worker_child_process = self._setup_processes()
        manager_process.terminate.side_effect = partial(self._successful_terminate_or_kill, manager_process)

        # Act
        self._stop_subcommand.run(None)

        # Assert
        self._assert_called_terminate([manager_process, worker_process, worker_child_process])
        self.assertFalse(manager_process.kill.called)
        self.assertTrue(worker_process.kill.called)
        self.assertTrue(worker_child_process.kill.called)
