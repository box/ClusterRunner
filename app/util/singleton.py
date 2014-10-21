from threading import RLock


class Singleton(object):

    _instance_lock = RLock()
    _singleton_instance = None

    @classmethod
    def singleton(cls):
        """
        Get the singleton instance. Create it if it doesn't exist.
        """
        with cls._instance_lock:
            if cls._singleton_instance is None:
                cls._singleton_instance = cls()
        return cls._singleton_instance

    @classmethod
    def reset_singleton(cls):
        """
        Reset the singleton instance.
        """
        with cls._instance_lock:
            if cls._singleton_instance is not None:
                del cls._singleton_instance
            cls._singleton_instance = None

    def __init__(self):
        """
        Raise an error if we attempt to instantiate multiple instances.

        Note that we *could* make every instantiation return the same instance -- Python allows this -- but have chosen
        not to. This is because we do not want client code to be ignorant of the fact that this object is a singleton.
        """
        with self._instance_lock:
            if self._singleton_instance is not None:
                raise SingletonError('Cannot instantiate singleton more than once. Use the singleton() class method.')


class SingletonError(Exception):
    """
    Raised when a singleton has been misused (e.g., instantiated more than once.)
    """
