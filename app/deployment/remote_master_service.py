from app.client.service_runner import ServiceRunner
from app.deployment.remote_service import RemoteService


class RemoteMasterService(RemoteService):
    """
    This class serves to start the master service remotely.
    """
    # Number of seconds to wait for master service to respond after starting
    _MASTER_SERVICE_TIMEOUT_SEC = 5

    def start_and_block_until_up(self, port, timeout_sec=_MASTER_SERVICE_TIMEOUT_SEC):
        """
        Start the clusterrunner master service and block until the master responds to web requests. Times out
        and throws an exception after timeout_sec.

        :param port: the port that the master service will run on
        :type port: int
        :param timeout_sec: number of seconds to wait for the master to respond before timing out
        :type timeout_sec: int
        """
        self._execute_ssh_command('nohup {} master --port {} &'.format(self._executable_path, str(port)), async=True)
        master_service_url = '{}:{}'.format(self.host, str(port))
        master_service = ServiceRunner(master_service_url)

        if not master_service.is_up(master_service_url, timeout=timeout_sec):
            self._logger.error('Master service running on {} failed to start.'.format(master_service_url))
            raise SystemExit(1)
