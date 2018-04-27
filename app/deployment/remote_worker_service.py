import socket

from app.deployment.remote_service import RemoteService


class RemoteWorkerService(RemoteService):
    """
    This class serves to start the worker service remotely.
    """

    def start(self, manager_host, manager_port, worker_port, num_executors):
        """
        Start the clusterrunner manager service and block until the manager responds to web requests. Times out
        and throws an exception after timeout_sec.

        :param manager_host: the host that the manager service is running on
        :type manager_host: str
        :param manager_port: the port that the manager service is running on
        :type manager_port: int
        :param worker_port: the port that this worker service will run on
        :type worker_port: int
        :param num_executors: the number of concurrent executors that will run in this worker service
        :type num_executors: int
        """
        if manager_host == 'localhost':
            manager_host = socket.gethostname()
        worker_args = '--manager-url {}:{}'.format(manager_host, str(manager_port))
        worker_args += ' --port {}'.format(str(worker_port))
        worker_args += ' --num-executors {}'.format(str(num_executors))
        self._shell_client.exec_command('nohup {} worker {} &'.format(self._executable_path, worker_args), async=True)
