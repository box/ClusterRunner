import time


def wait_for(boolean_predicate, timeout_seconds=None, poll_period=0.25, exceptions_to_swallow=None):
    """
    Waits a specified amount of time for the conditional predicate to be true.

    :param boolean_predicate: A callable to continually evaluate until it returns a truthy value
    :type boolean_predicate: callable
    :param timeout_seconds: The timeout (in seconds)
    :type timeout_seconds: int
    :param poll_period: The frequency at which boolean_predicate should be evaluated
    :type poll_period: float
    :param exceptions_to_swallow: A set of acceptable exceptions that may be thrown by boolean_predicate
    :type exceptions_to_swallow: Exception | list(Exception)
    :return: True if boolean_predicate returned True before the timeout; False otherwise
    :rtype: bool
    """
    exceptions_to_swallow = exceptions_to_swallow or ()
    timeout_seconds = timeout_seconds or float('inf')

    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        try:
            if boolean_predicate():
                return True
        except exceptions_to_swallow:
            pass

        time.sleep(poll_period)
    return False
