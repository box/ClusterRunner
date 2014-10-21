from app.util.shell.factory import ShellClientFactory


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
        self._host = host
        self._username = username
        self._executable_path = executable_path
        self._shell_client = ShellClientFactory.create(host, username)

    def stop(self):
        """
        Stop all clusterrunner services on this machine. This functionality is in the base class because it
        should be common across all possible subclasses.
        """
        self._execute_ssh_command('{} stop'.format(self._executable_path))

    def _execute_ssh_command(self, command):
        """
        Helper method for executing ssh commands.

        :param command: command to execute remotely
        :type command: str
        """
        self._shell_client.connect()

        # Run these commands asynchronously because they are services...
        self._shell_client.exec_command(command, async=True)
        self._shell_client.close()

    def host(self):
        """
        :return:
        :rtype: str
        """
        return self._host