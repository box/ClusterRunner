from app.util.log import get_logger
from app.util.shell.shell_client_factory import ShellClientFactory


class RemoteService(object):
    """
    Parent class for manipulating clusterrunner services on remote hosts (through ssh).
    """

    def __init__(self, host, username, executable_path):
        """
        :param host: the fully qualified hostname of the host to deploy to
        :type host: str
        :param username: the user who is executing this process and whose ssh credentials will be used
        :type username: str
        :param executable_path: the path to the clusterrunner executable on the remote host
        :type executable_path: str
        """
        self._logger = get_logger(__name__)
        self.host = host
        self._username = username
        self._executable_path = executable_path
        self._shell_client = ShellClientFactory.create(host, username)

    def stop(self):
        """
        Stop all clusterrunner services on this machine. This functionality is in the base class because it
        should be common across all possible subclasses.
        """
        response = self._shell_client.exec_command('{} stop'.format(self._executable_path), async=False)

        if not response.is_success():
            self._logger.error('clusterrunner stop failed on host {} with output: {}, error: {}'.format(
                self.host, response.raw_output, response.raw_error))
