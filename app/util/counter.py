from queue import Queue


class Counter(object):
    """
    A thread-safe counter.
    """
    def __init__(self, start=0, step=1):
        self._step = step
        self._counter = Queue(maxsize=1)
        self._counter.put(start)

    def increment(self):
        return self._change_current_value(self._step)

    def decrement(self):
        return self._change_current_value(-self._step)

    def value(self):
        return self._change_current_value(0)

    def _change_current_value(self, delta):
        i = self._counter.get()  # will block until another thread finishes calling put
        self._counter.put(i + delta)
        return i + delta
