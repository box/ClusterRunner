import functools

from app.manager.cluster_manager import ClusterManager
from app.subcommands.service_subcommand import ServiceSubcommand
from app.util import analytics, log
from app.util.conf.configuration import Configuration
from app.web_framework.cluster_manager_application import ClusterManagerApplication


class ManagerSubcommand(ServiceSubcommand):
    _THREAD_NAME = 'ManagerTornadoThread'

    def async_run(self, port, log_level, eventlog_file):
        """
        Run a ClusterRunner manager service.

        :param port: the port on which to run the worker service
        :type port: int | None
        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param eventlog_file: an optional alternate file in which to write event logs
        :type eventlog_file: str | None
        """
        port = port or Configuration['port']
        log_level = log_level or Configuration['log_level']
        eventlog_file = eventlog_file or Configuration['eventlog_file']

        log.configure_logging(log_level=log_level, log_file=Configuration['log_file'])
        analytics.initialize(eventlog_file)
        analytics.record_event(analytics.SERVICE_STARTED, service='manager')

        cluster_manager = ClusterManager()

        application = ClusterManagerApplication(cluster_manager)

        ioloop = self._start_application(application, port)

        self._write_pid_file(Configuration['manager_pid_file'])

        # log startup message once ioloop is running
        hostname = Configuration['hostname']
        log_startup = functools.partial(self._logger.info, 'Manager service is running on {}:{}.'.format(hostname, port))
        ioloop.add_callback(log_startup)

        # start heartbeat tracker once ioloop starts
        start_manager_heartbeat_tracker = functools.partial(cluster_manager.start_heartbeat_tracker_thread)
        ioloop.add_callback(start_manager_heartbeat_tracker)

        ioloop.start()  # this call blocks until the server is stopped
        ioloop.close(all_fds=True)  # all_fds=True is necessary here to make sure connections don't hang
        self._logger.notice('Manager server was stopped.')
