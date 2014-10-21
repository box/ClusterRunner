import time


def wait_for(boolean_predicate, timeout_seconds, poll_period=0.25, exceptions_to_swallow=None):
    """
    Waits a specified amount of time for the conditional predicate to be true.

    :param lambda boolean_predicate:
    :param int timeout_seconds: the timeout (in seconds)
    :param float poll_period:
    :param exceptions_to_swallow:
    :return bool
    """
    exceptions_to_swallow = exceptions_to_swallow or []
    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        try:
            if boolean_predicate():
                return True
        except exceptions_to_swallow:
            pass

        time.sleep(poll_period)
    return False
