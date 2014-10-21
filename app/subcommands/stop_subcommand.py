import os
import psutil
import signal
import time

from app.subcommands.subcommand import Subcommand
from app.util import log
from app.util.conf.configuration import Configuration


class StopSubcommand(Subcommand):

    # The commands that can be used to identify a clusterrunner process (for accurate killing).
    _command_whitelist_keywords = ['clusterrunner', 'main.py master', 'main.py slave']
    # The number of seconds to wait between performing a SIGTERM and a SIGKILL
    _sigterm_sigkill_grace_period_sec = 2

    def run(self, log_level):
        """
        Stop/kill all ClusterRunner processes that are running on this host (both master and slave services).
        This is implemented via the pid file that gets written to upon service startup.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        """
        log_level = log_level or Configuration['log_level']
        log.configure_logging(log_level=log_level)
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
                "PID {0} is running, but command '{1}' is not a clusterrunner command".format(pid, proc_command))
            return

        # Try killing gracefully with SIGTERM first. Then give process some time to gracefully shutdown. If it
        # doesn't, perform a SIGKILL.
        # @TODO: use util.timeout functionality once it gets merged
        os.kill(int(pid), signal.SIGTERM)
        sigterm_start = time.time()

        while (time.time()-sigterm_start) <= self._sigterm_sigkill_grace_period_sec:
            if not psutil.pid_exists(int(pid)):
                break
            time.sleep(0.1)

        if psutil.pid_exists(int(pid)):
            self._logger.info("SIGTERM signal to PID {0} failed. Killing with SIGKILL".format(pid))
            os.kill(int(pid), signal.SIGKILL)
            return

        self._logger.info("Killed process with PID {0} with SIGTERM".format(pid))
