import time

from app.client.service_runner import ServiceRunner
from app.deployment.remote_service import RemoteService


class RemoteMasterService(RemoteService):
    """
    This class serves to start the master service remotely.
    """
    # Number of seconds to wait for master service to respond after starting
    _MASTER_SERVICE_TIMEOUT_SEC = 45
    # The number of times to retry starting the master daemon
    _MASTER_SERVICE_START_RETRIES = 3

    def start_and_block_until_up(self, port, timeout_sec=_MASTER_SERVICE_TIMEOUT_SEC):
        """
        Start the clusterrunner master service and block until the master responds to web requests. Times out
        and throws an exception after timeout_sec.

        :param port: the port that the master service will run on
        :type port: int
        :param timeout_sec: number of seconds to wait for the master to respond before timing out
        :type timeout_sec: int
        """
        # Start the master service daemon
        master_service_cmd = 'nohup {} master --port {} &'.format(self._executable_path, str(port))

        # There are cases when 'clusterrunner deploy' fails, and there is no clusterrunner master service process
        # to be seen--but the fix is to just re-run the command.
        for i in range(self._MASTER_SERVICE_START_RETRIES):
            self._shell_client.exec_command(master_service_cmd, async=True)
            # Give the service a second to start up
            time.sleep(1)

            if self._is_process_running(self._executable_path):
                break
            else:
                self._logger.warning('Master service process failed to start on try {}, host {}'.format(i, self.host))

        if not self._is_process_running(self._executable_path):
            self._logger.error('Master service process failed to start on host {}.'.format(self.host))
            raise SystemExit(1)

        # Check to see if the master service is responding to http requests
        master_service_url = '{}:{}'.format(self.host, str(port))
        master_service = ServiceRunner(master_service_url, main_executable=self._executable_path)

        if not master_service.is_up(master_service_url, timeout=timeout_sec):
            self._logger.error('Master service process exists on {}, but service on {} failed to respond.'.format(
                self.host, master_service_url))
            raise SystemExit(1)

    def _is_process_running(self, command):
        """
        Is a process that contains the string command running on the remote host?

        :param command: The command substring to search for.
        :type command: str
        :rtype: bool
        """
        # Replace first char of command, 'n', with '[n]' to prevent the grep call from showing up in search results
        command = '[{}]'.format(command[0]) + command[1:]

        # Because this shell_client call can potentially be remote, we cannot use the psutil library, and
        # must instead perform shell commands directly.
        ps_search_cmd = 'ps ax | grep \'{}\''.format(command)
        ps_search_response = self._shell_client.exec_command(ps_search_cmd, async=False)
        output = ps_search_response.raw_output.decode("utf-8").split("\n")

        for output_line in output:
            if len(output_line.strip()) == 0:
                continue
            return True

        return False
