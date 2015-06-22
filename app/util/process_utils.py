from contextlib import suppress
import os
import subprocess
from subprocess import TimeoutExpired


def kill_gracefully(process, timeout=2):
    """
    Try terminating the process first (uses SIGTERM; which allows it to potentially shutdown gracefully). If the process
    does not exit within the given timeout, the process is killed (SIGKILL).

    :param process: The process to terminate or kill
    :type process: Popen
    :param timeout: Number of seconds to wait after terminate before killing
    :type timeout: int
    :return: The exit code, stdout, and stderr of the process
    :rtype: (int, str, str)
    """
    try:
        with suppress(ProcessLookupError):
            process.terminate()
        stdout, stderr = process.communicate(timeout=timeout)
    except TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()

    return process.returncode, stdout, stderr


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
    if os.name == 'nt':
        cmd_with_deplayed_expansion = ['cmd', '/V', '/C']
        if isinstance(cmd, str):
            cmd_with_deplayed_expansion.append(cmd)
        else:
            cmd_with_deplayed_expansion.extend(cmd)
        cmd = cmd_with_deplayed_expansion
    return subprocess.Popen(cmd, *args, **kwargs)
