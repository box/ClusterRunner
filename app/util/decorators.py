from functools import wraps
import time

from app.util import log
from app.util.exceptions import AuthenticationError
from app.util.secret import Secret


def retry_on_exception(exceptions, num_attempts=10, retry_delay=0.1):

    def method_decorator(function):
        @wraps(function)
        def function_with_retries(*args, **kwargs):
            for i in range(num_attempts):
                try:
                    return_value = function(*args, **kwargs)
                except exceptions as ex:
                    if i == num_attempts - 1:
                        raise  # final attempt failed
                    log.get_logger(__name__).warning('Call to {} raised {}("{}"). Retrying in {} seconds.',
                                                     function.__qualname__, type(ex).__name__, ex, retry_delay)
                    time.sleep(retry_delay)
                else:
                    return return_value

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
