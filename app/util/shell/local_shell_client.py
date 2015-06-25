import shutil
from subprocess import PIPE, DEVNULL

from app.util.log import get_logger
from app.util.process_utils import Popen_with_delayed_expansion
from app.util.shell.shell_client import ShellClient, Response, EmptyResponse


class LocalShellClient(ShellClient):
    def __init__(self, host, user):
        super().__init__(host, user)
        self._logger = get_logger(__name__)

    def _exec_command_on_client_async(self, command):
        """
        :param command:
        :return:
        :rtype: Response
        """
        # todo investigate why this assignment is required for launching async operations using Popen
        self._logger.debug('popen async [{}:{}]: {}'.format(self.user, self.host, command))
        Popen_with_delayed_expansion(command, shell=True, stdout=DEVNULL, stderr=DEVNULL)
        return EmptyResponse()

    def _exec_command_on_client_blocking(self, command):
        """
        :param command:
        :type command: str
        :return:
        :rtype: Response
        """
        proc = Popen_with_delayed_expansion(command, shell=True, stdout=PIPE, stderr=PIPE)
        self._logger.debug('popen blocking [{}:{}]: {}'.format(self.user, self.host, command))
        output, error = proc.communicate()
        return Response(raw_output=output, raw_error=error, returncode=proc.returncode)

    def _copy_on_client(self, source, destination):
        """
        :param source:
        :type source: str
        :param destination:
        :type destination: str
        :return:
        :rtype: Response
        """
        new_location = shutil.copy(source, destination)
        # todo detect failure and specify returncode and error
        return Response(raw_output=new_location.encode(), returncode=0)
