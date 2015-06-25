from subprocess import PIPE, DEVNULL

from app.util.log import get_logger
from app.util.process_utils import Popen_with_delayed_expansion
from app.util.shell.shell_client import ShellClient, Response, EmptyResponse


class RemoteShellClient(ShellClient):
    def __init__(self, host, user):
        super().__init__(host, user)
        self._logger = get_logger(__name__)

    def _exec_command_on_client_async(self, command):
        """
        :type command: str
        :rtype: Response
        """
        escaped_command = self._escaped_ssh_command(command)
        self._logger.debug('SSH popen async [{}:{}]: {}'.format(self.user, self.host, escaped_command))
        Popen_with_delayed_expansion(escaped_command, shell=True, stdout=DEVNULL, stderr=DEVNULL)
        return EmptyResponse()

    def _exec_command_on_client_blocking(self, command):
        """
        :type command: str
        :rtype: Response
        """
        escaped_command = self._escaped_ssh_command(command)
        self._logger.debug('SSH popen blocking [{}:{}]: {}'.format(self.user, self.host, escaped_command))
        proc = Popen_with_delayed_expansion(escaped_command, shell=True, stdout=PIPE, stderr=PIPE)
        output, error = proc.communicate()
        return Response(raw_output=output, raw_error=error, returncode=proc.returncode)

    def _copy_on_client(self, source, destination):
        """
        :type source: str
        :type destination: str
        :rtype: Response
        """
        # Avoid any ssh known_hosts prompts.
        command = 'scp -o StrictHostKeyChecking=no {} {}:{}'.format(source, self._host_string(), destination)
        self._logger.debug('SCP popen blocking [{}:{}]: {}'.format(self.user, self.host, command))
        proc = Popen_with_delayed_expansion(command, shell=True, stdout=PIPE, stderr=PIPE)
        output, error = proc.communicate()
        return Response(raw_output=output, raw_error=error, returncode=proc.returncode)

    def _escaped_ssh_command(self, command):
        """
        :param command: the command to execute if it were local
        :type command: str
        :return: the escaped command wrapped around an ssh call
        :rtype: str
        """
        escaped_command = command.replace("'", "\'")
        # Avoid any ssh known_hosts prompts.
        return "ssh -o StrictHostKeyChecking=no {} '{}'".format(self._host_string(), escaped_command)

    def _host_string(self):
        """
        Return either the host, or the username@host if the username is specified.

        :rtype: str
        """
        return self.host if self.user is None else "{}@{}".format(self.user, self.host)
