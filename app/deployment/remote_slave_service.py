import socket

from app.deployment.remote_service import RemoteService


class RemoteSlaveService(RemoteService):
    """
    This class serves to start the slave service remotely.
    """

    def start(self, master_host, master_port, slave_port, num_executors):
        """
        Start the clusterrunner master service and block until the master responds to web requests. Times out
        and throws an exception after timeout_sec.

        :param master_host: the host that the master service is running on
        :type master_host: str
        :param master_port: the port that the master service is running on
        :type master_port: int
        :param slave_port: the port that this slave service will run on
        :type slave_port: int
        :param num_executors: the number of concurrent executors that will run in this slave service
        :type num_executors: int
        """
        if master_host == 'localhost':
            master_host = socket.gethostname()
        slave_args = '--master-url {}:{}'.format(master_host, str(master_port))
        slave_args += ' --port {}'.format(str(slave_port))
        slave_args += ' --num-executors {}'.format(str(num_executors))
        self._shell_client.exec_command('nohup {} slave {} &'.format(self._executable_path, slave_args), async=True)
