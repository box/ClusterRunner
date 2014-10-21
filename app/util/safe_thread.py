from threading import Thread

from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class SafeThread(Thread):
    """
    This class represents an application thread that should not be allowed to raise an exception without also shutting
    down the entire application. Any exceptions raised from this thread will be funneled through the unhandled
    exception handler.

    Unless we have a specific reason not to, we should use this class everywhere throughout the application instead of
    threading.Thread.
    """
    def run(self):
        unhandled_exception_handler = UnhandledExceptionHandler.singleton()
        with unhandled_exception_handler:
            super().run()
