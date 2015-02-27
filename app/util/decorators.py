from functools import wraps
import time

from app.util import log
from app.util.exceptions import AuthenticationError
from app.util.secret import Secret


def retry_on_exception_exponential_backoff(exceptions, initial_delay=0.1, total_delay=15, exponential_factor=2):
    """
    Retries with exponential backoff.

    :param exceptions: The exceptions that we will catch and retry on.
    :type exceptions: list[Exception]
    :param initial_delay: num seconds that the first retry period will be
    :type initial_delay: float
    :param total_delay: the total number of seconds of the sum of all retry periods
    :type total_delay: float
    :param exponential_factor: Cannot be smaller than 1.
    :type exponential_factor: float
    """
    def method_decorator(function):
        @wraps(function)
        def function_with_retries(*args, **kwargs):
            # If initial_delay is negative, then exponentiation would go infinitely.
            if initial_delay <= 0:
                raise RuntimeError('initial_delay must be greater than 0, was set to {}'.format(str(initial_delay)))

            # The exponential factor must be greater than 1.
            if exponential_factor <= 1:
                raise RuntimeError('exponential_factor, {}, must be greater than 1'.format(exponential_factor))

            delay = initial_delay
            total_delay_so_far = 0

            while True:
                try:
                    return function(*args, **kwargs)
                except exceptions as ex:
                    if total_delay_so_far > total_delay:
                        raise  # final attempt failed
                    log.get_logger(__name__).warning('Call to {} raised {}("{}"). Retrying in {} seconds.',
                                                     function.__qualname__, type(ex).__name__, ex, delay)
                    time.sleep(delay)
                    total_delay_so_far += delay
                    delay *= exponential_factor

        return function_with_retries
    return method_decorator


def authenticated(function):
    """
    Fail the request if the correct secret is not included in either the headers or the request body. This should be
    called on all mutation requests. (POST, PUT)
    """
    @wraps(function)
    def function_with_auth(self, *args, **kwargs):
        header_digest = self.request.headers.get(Secret.DIGEST_HEADER_KEY)
        if not Secret.digest_is_valid(header_digest, self.encoded_body.decode('utf-8')):
            raise AuthenticationError('Message digest does not match header, message not authenticated.')

        return function(self, *args, **kwargs)

    return function_with_auth
