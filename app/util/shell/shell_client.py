class ShellClient(object):
    """
    Shell Client interface
    """
    def __init__(self, host, user):
        self.host = host
        self.user = user

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

    def copy(self, source, destination, error_on_failure=False):
        """
        Copies the item from the source to the destination
        :param source:
        :type source: str
        :param destination:
        :type destination: str
        :return:
        """
        res = self._copy_on_client(source, destination)
        if error_on_failure and not res.is_success():
            error_message = 'Copy from "{}" to "{}" failed with:\nerror: {}\noutput: {}\nexit code: {}'.format(
                source,
                destination,
                res.raw_error,
                res.raw_output,
                res.returncode,
            )
            raise RuntimeError(error_message)
        else:
            return res

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

    def __eq__(self, other):
        """
        Checks member equaivalence between self and another response
        :param other: Another response object
        :type other: Response
        :return: True if they have member equivalence, False otherwise
        :rtype: bool
        """
        return (
            isinstance(other, type(self)) and
            self.raw_output == other.raw_output and
            self.raw_error == other.raw_error and
            self.returncode == other.returncode
        )


class EmptyResponse(Response):
    pass
