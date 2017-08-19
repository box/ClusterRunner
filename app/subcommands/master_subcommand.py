import functools

from app.master.cluster_master import ClusterMaster
from app.subcommands.service_subcommand import ServiceSubcommand
from app.util import analytics, log
from app.util.conf.configuration import Configuration
from app.web_framework.cluster_master_application import ClusterMasterApplication


class MasterSubcommand(ServiceSubcommand):
    _THREAD_NAME = 'MasterTornadoThread'

    def async_run(self, port, log_level, eventlog_file):
        """
        Run a ClusterRunner master service.

        :param port: the port on which to run the slave service
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
        analytics.record_event(analytics.SERVICE_STARTED, service='master')

        cluster_master = ClusterMaster()
        application = ClusterMasterApplication(cluster_master)

        ioloop = self._start_application(application, port)

        self._write_pid_file(Configuration['master_pid_file'])

        # log startup message once ioloop is running
        hostname = Configuration['hostname']
        log_startup = functools.partial(self._logger.info, 'Master service is running on {}:{}.'.format(hostname, port))
        ioloop.add_callback(log_startup)

        ioloop.start()  # this call blocks until the server is stopped
        ioloop.close(all_fds=True)  # all_fds=True is necessary here to make sure connections don't hang
        self._logger.notice('Master server was stopped.')
