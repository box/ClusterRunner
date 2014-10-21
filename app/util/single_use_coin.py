from threading import Lock


class SingleUseCoin(object):
    """
    A SingleUseCoin acts as a thread-safe, one-time flag. For example, this is useful for enforcing that a specific
    code path is only traversed exactly once, even across multiple threads.

    The first time spend() is called, it will return True. All subsequent calls to spend() will return False. If many
    threads call spend(), it is guaranteed that exactly one will return True.
    """
    def __init__(self):
        self._is_spent = False
        self._spend_lock = Lock()

    def spend(self):
        """
        Returns whether or not the coin was spent. The coin can only be spent one time.

        :return: True the first time that this method is called, False all subsequent calls
        :rtype: bool
        """
        with self._spend_lock:
            if self._is_spent:
                return False

            self._is_spent = True
            return True
