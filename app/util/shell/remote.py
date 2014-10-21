from paramiko import SSHClient, AutoAddPolicy

from app.util.log import get_logger
from app.util.shell.shell_client import ShellClient, Response, EmptyResponse


class RemoteShellClient(ShellClient):
    def __init__(self, host, user):
        super().__init__(host, user)
        self._logger = get_logger(__name__)
        self._ssh = None
        """ :type : SSHClient"""

    def _connect_client(self):
        if self._ssh is None:
            self._ssh = SSHClient()
            self._ssh.set_missing_host_key_policy(AutoAddPolicy())
        self._ssh.connect(self.host, username=self.user)

    def _close_client(self):
        self._ssh.close()

    def _exec_command_on_client_async(self, command):
        """
        :param command:
        :type command: str
        :return:
        :rtype: Response
        """
        self._logger.debug('SSH async [{}:{}]: {}'.format(self.user, self.host, command))
        self._ssh.exec_command(command)
        # todo add a callback to get the real response values
        return EmptyResponse()

    def _exec_command_on_client_blocking(self, command):
        """
        :param command:
        :type command: str
        :return:
        :rtype: Response
        """
        channel_file_to_bytes = lambda x: ''.join(x.readlines()).encode()
        self._logger.debug('SSH blocking [{}:{}]: {}'.format(self.user, self.host, command))
        _, stdout, stderr = self._ssh.exec_command(command)
        returncode = stdout.channel.recv_exit_status()
        return Response(
            raw_output=channel_file_to_bytes(stdout),
            raw_error=channel_file_to_bytes(stderr),
            returncode=returncode
        )

    def _copy_on_client(self, source, destination):
        """
        :param source:
        :type source: str
        :param destination:
        :type destination: str
        :return:
        :rtype: Response
        """
        sftp = self._ssh.open_sftp()
        sftp.put(source, destination)
        # todo add callback to fill real response values from async sftp put
        return EmptyResponse()
