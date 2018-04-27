import functools
import os
import sys
import tornado.ioloop
from tornado.httpserver import HTTPServer

from app.util.conf.configuration import Configuration
from app.subcommands.subcommand import Subcommand
from app.util import fs
from app.util.safe_thread import SafeThread
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class ServiceSubcommand(Subcommand):
    """
    Base class for Manager and Worker subcommands.
    """
    _THREAD_NAME = None

    def run(self, *args, **kwargs):
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
            # If SSL cert and key files are provided in configuration, ClusterRunner wil start with HTTPS protocol.
            # Otherwise ClusterRunner will start with HTTP protocol.
            server = HTTPServer(application, ssl_options=self._get_https_options())
            server.listen(port, '0.0.0.0')
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

    def _get_https_options(self):
        https_cert_file = Configuration['https_cert_file']
        https_key_file = Configuration['https_key_file']

        if https_cert_file and https_key_file:
            return {
                'certfile': https_cert_file,
                'keyfile': https_key_file,
            }
        return None
