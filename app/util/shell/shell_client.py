import socket


class ShellClient(object):
    """
    Shell Client interface
    """
    def __init__(self, host, user):
        self.host = host
        self.user = user
        self.connected = False

    def connect(self):
        """
        Initializes the shell connection with the host
        :return:
        """
        if not self.connected:
            self.connected = True
            self._connect_client()
        else:
            raise ConnectionError('Connection to host {} as user {} is already open'.format(self.host, self.user))

    def _connect_client(self):
        """ Put subclass implementation here """
        pass

    def close(self):
        """
        Closes the shell connection with the host
        :return:
        """
        if self.connected:
            self.connected = False
            self._close_client()
        else:
            raise ConnectionAbortedError('Connection to host {} as user {}'.format(self.host, self.user))

    def _close_client(self):
        """ Put subclass implementation here """
        pass

    @classmethod
    def is_localhost(cls, host):
        """
        :param host:
        :return:
        :rtype: bool
        """
        return (
            'localhost' == host or
            socket.gethostbyname(host) == socket.gethostbyname(socket.gethostname())
        )

    def exec_command(self, command, async=False, error_on_failure=False):
        """
        Executes a command on the host
        :param command:
        :type command: str
        :param async: option to execute as a non-blocking call
        :type async: bool
        :param error_on_failure: option to raise a failure if the shell exit code is not a success
        :type error_on_failure: bool
        :return:
        :rtype: Response
        """
        if not self.connected:
            raise ConnectionError(
                'Connection to host {}  as user {} is closed, unable to exececute command {}'.format(
                    self.host, self.user, command
                )
            )
        if async and error_on_failure:
            raise NotImplementedError('async command execution and raising errors on failure is not implemented')
        elif async:
            return self._exec_command_on_client_async(command)
        else:
            res = self._exec_command_on_client_blocking(command)
            if error_on_failure and not res.is_success():
                error_message = 'Command "{}" on host "{}" as user "{}" failed with exit code: {}.'.format(
                    command, self.host, self.user, res.returncode
                )
                raise RuntimeError(error_message)
            else:
                return res

    def _exec_command_on_client_async(self, command):
        """
        Put subclass implementation here
        :param command:
        :return:
        :rtype: Response
        """
        raise NotImplementedError('async command execution not implemented')

    def _exec_command_on_client_blocking(self, command):
        """
        Put subclass implementation here
        :param command:
        :type command: str
        :return:
        :rtype: Response
        """
        raise NotImplementedError('blocking command execution not implemented')

    def copy(self, source, destination):
        """
        Copies the item from the source to the destination
        :param source:
        :type source: str
        :param destination:
        :type destination: str
        :return:
        """
        if not self.connected:
            raise ConnectionError(
                'Connection to host {}  as user {} is closed, unable to copy {} to {}'.format(
                    self.host,
                    self.user,
                    source,
                    destination
                )
            )
        return self._copy_on_client(source, destination)

    def _copy_on_client(self, source, destination):
        """
        Put subclass implementation here
        :param source:
        :type source: str
        :param destination:
        :type destination: str
        :return:
        """
        raise NotImplementedError('copy command not implemented')


class Response(object):
    """
    Represents a response from the SSHClient. By convention, asynchronous operations
    should register a callback with a response, and access use that callback to check
    completion of async operations
    """
    def __init__(self, raw_output=None, raw_error=None, returncode=None):
        """
        :param raw_output:
        :type raw_output: bytes | None
        :param raw_error:
        :type raw_error: bytes | None
        :param returncode:
        :type returncode: int | None
        """
        self.raw_output = raw_output
        self.raw_error = raw_error
        self.returncode = returncode

    def is_success(self):
        """
        :return:
        :rtype: bool
        """
        return self.returncode == 0

    def compare_to(self, response):
        """
        Checks member equaivalence between self and another response
        :param response:
        :type response: Response
        :return: True if they have member equivalence, False otherwise
        :rtype: bool
        """
        return (
            self.raw_output == response.raw_output and
            self.raw_error == response.raw_error and
            self.returncode == response.returncode
        )


class EmptyResponse(Response):
    pass
