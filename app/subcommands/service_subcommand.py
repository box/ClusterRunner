import functools
import multiprocessing
import os
import sys
import tornado.ioloop

from app.subcommands.subcommand import Subcommand
from app.util import fs
from app.util.safe_thread import SafeThread
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class ServiceSubcommand(Subcommand):
    """
    Base class for Master and Slave subcommands.
    """
    _THREAD_NAME = None

    def run(self, *args, **kwargs):
        # Set the multiprocessing method to 'spawn'. (The default on unix is 'fork'.) According to documentation, this
        # method should be called at most once, which is why it is here and not in the Git class. This prevents any
        # subprocesses started by the multiprocessing library from inheriting the parent file descriptors. This is a
        # vital fix for a very specific issue. See https://github.com/box/ClusterRunner/issues/69 for more details.
        multiprocessing.set_start_method('spawn')  # pylint: disable=no-member

        app_thread = SafeThread(
            name=self._THREAD_NAME,
            target=self.async_run,
            args=args,
            kwargs=kwargs,
        )
        app_thread.start()
        app_thread.join()

    def async_run(self, *args, **kwargs):
        raise NotImplementedError

    def _start_application(self, application, port):
        # Note: No significant application logic should be executed before this point. The call to application.listen()
        # will raise an exception if another process is using the same port. We rely on this exception to force us to
        # exit if there are any port conflicts.
        try:
            application.listen(port, '0.0.0.0')
        except OSError:
            self._logger.error('Could not start application on port {}. Is port already in use?'.format(port))
            sys.exit(1)

        ioloop = tornado.ioloop.IOLoop.instance()

        # add a teardown callback that will stop the tornado server
        stop_tornado_ioloop = functools.partial(ioloop.add_callback, callback=ioloop.stop)
        UnhandledExceptionHandler.singleton().add_teardown_callback(stop_tornado_ioloop)
        return ioloop

    def _write_pid_file(self, filename):
        fs.write_file(str(os.getpid()), filename)

        def remove_pid_file():
            try:
                os.remove(filename)
            except OSError:
                pass
        UnhandledExceptionHandler.singleton().add_teardown_callback(remove_pid_file)
