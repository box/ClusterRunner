import os
import time

import psutil

from app.subcommands.subcommand import Subcommand
from app.util import log
from app.util.conf.configuration import Configuration


class StopSubcommand(Subcommand):

    # The commands that can be used to identify a clusterrunner process (for accurate killing).
    _command_whitelist_keywords = ['clusterrunner', 'main.py master', 'main.py slave']
    # The number of seconds to wait between performing a SIGTERM and a SIGKILL
    SIGTERM_SIGKILL_GRACE_PERIOD_SEC = 2

    def run(self, log_level):
        """
        Stop/kill all ClusterRunner processes that are running on this host (both master and slave services).
        This is implemented via the pid file that gets written to upon service startup.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        """
        log.configure_logging(
            log_level=log_level or Configuration['log_level'],
            log_file=Configuration['log_file'],
            simplified_console_logs=True,
        )
        self._kill_pid_in_file_if_exists(Configuration['slave_pid_file'])
        self._kill_pid_in_file_if_exists(Configuration['master_pid_file'])

    def _kill_pid_in_file_if_exists(self, pid_file_path):
        """
        Kill the process referred to by the pid in the pid_file_path if it exists and the process with pid is running.

        :param pid_file_path: the path to the pid file (that should only contain the pid if it exists at all)
        :type pid_file_path: str
        """
        if not os.path.exists(pid_file_path):
            self._logger.info("Pid file {0} does not exist.".format(pid_file_path))
            return

        with open(pid_file_path, 'r') as f:
            pid = f.readline()

        if not psutil.pid_exists(int(pid)):
            self._logger.info("Pid file {0} exists, but pid {1} doesn't exist.".format(pid_file_path, pid))
            os.remove(pid_file_path)
            return

        # Because PIDs are re-used, we want to verify that the PID corresponds to the correct command.
        proc = psutil.Process(int(pid))
        proc_command = ' '.join(proc.cmdline())
        matched_proc_command = False

        for command_keyword in self._command_whitelist_keywords:
            if command_keyword in proc_command:
                matched_proc_command = True
                break

        if not matched_proc_command:
            self._logger.info(
                "PID {0} is running, but command '{1}' is not a clusterrunner command".format(proc.pid, proc_command))
            return

        # Try killing gracefully with SIGTERM first. Then give process some time to gracefully shutdown. If it
        # doesn't, perform a SIGKILL.
        # @TODO: use util.timeout functionality once it gets merged
        procs_to_kill = proc.children(recursive=True) + [proc]
        self._terminate_running_procs(procs_to_kill)
        sigterm_start = time.time()

        while (time.time()-sigterm_start) <= self.SIGTERM_SIGKILL_GRACE_PERIOD_SEC:
            if not any([proc_to_kill.is_running() for proc_to_kill in procs_to_kill]):
                break
            time.sleep(0.1)

        if any([proc_to_kill.is_running() for proc_to_kill in procs_to_kill]):
            self._kill_running_procs(procs_to_kill)
            return
        else:
            self._logger.info("Killed all running clusterrunner processes with SIGTERM")

    def _terminate_running_procs(self, procs_to_termintate):
        for proc in [p for p in procs_to_termintate if p.is_running()]:
            self._logger.info("Terminating process with PID {}", proc.pid)
            proc.terminate()

    def _kill_running_procs(self, procs_to_kill):
        for proc in [p for p in procs_to_kill if p.is_running()]:
            self._logger.info("Killing process with PID {}", proc.pid)
            proc.kill()
