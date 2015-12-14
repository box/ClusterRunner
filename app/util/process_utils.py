from contextlib import suppress
import os
import subprocess
import time


SIGINFO = 29  # signal.SIGINFO is not present in all Python distributions


def kill_gracefully(process, timeout=2):
    """
    Try terminating the process first (uses SIGTERM; which allows it to potentially shutdown gracefully). If the process
    does not exit within the given timeout, the process is killed (SIGKILL).

    :param process: The process to terminate or kill
    :type process: subprocess.Popen
    :param timeout: Number of seconds to wait after terminate before killing
    :type timeout: int
    :return: The exit code, stdout, and stderr of the process
    :rtype: (int, str, str)
    """
    try:
        with suppress(ProcessLookupError):
            process.terminate()
        stdout, stderr = process.communicate(timeout=timeout)

    except subprocess.TimeoutExpired:
        if not is_windows():
            process.send_signal(SIGINFO)  # this assumes a debug handler has been registered for SIGINFO
            time.sleep(1)  # give the logger a chance to write out debug info
        process.kill()
        stdout, stderr = process.communicate()

    return process.returncode, stdout, stderr


def is_windows():
    """
    :return: Whether ClusterRunner is running on Windows or not>
    :rtype: bool
    """
    return os.name == 'nt'


def Popen_with_delayed_expansion(cmd, *args, **kwargs):
    """
    A thin wrapper around subprocess.Popen which ensures that all environment variables in the cmd are expanded at
    execution time. By default, Windows CMD *disables* delayed expansion which means it will expand the command first
    before execution. E.g. run 'set FOO=1 && echo %FOO%' won't actually echo 1 because %FOO% gets expanded before the
    execution.

    :param cmd: The command to execute
    :type cmd: str | iterable

    :return: Popen object, just like the Popen object returned by subprocess.Popen
    :rtype: :class:`Popen`
    """
    if is_windows():
        cmd_with_deplayed_expansion = ['cmd', '/V', '/C']
        if isinstance(cmd, str):
            cmd_with_deplayed_expansion.append(cmd)
        else:
            cmd_with_deplayed_expansion.extend(cmd)
        cmd = cmd_with_deplayed_expansion
    return subprocess.Popen(cmd, *args, **kwargs)


def get_environment_variable_setter_command(name, value):
    """
    Construct a platform specific command for setting an environment variable. Right now each command constructed
    is designed to be chained with other commands.

    :param name: The name of the environment variable
    :type name: str
    :param value: The value of the environment variable
    :type value: str
    :return: Platform specific command for setting the environment variable
    :rtype: str
    """
    if is_windows():
        return 'set {}={}&&'.format(name, value)
    else:
        return 'export {}="{}";'.format(name, value)
