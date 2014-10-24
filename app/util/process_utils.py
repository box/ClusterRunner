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
        process.terminate()
        stdout, stderr = process.communicate(timeout=timeout)
    except TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()

    return process.returncode, stdout, stderr
