import functools

from app.slave.cluster_slave import ClusterSlave
from app.subcommands.service_subcommand import ServiceSubcommand
from app.util import analytics, log
from app.util.conf.configuration import Configuration
from app.web_framework.cluster_slave_application import ClusterSlaveApplication


class SlaveSubcommand(ServiceSubcommand):
    _THREAD_NAME = 'SlaveTornadoThread'

    def async_run(self, port, master_url, num_executors, log_level, eventlog_file):
        """
        Run a ClusterRunner slave service.

        :param port: the port on which to run the slave service
        :type port: int | None
        :param master_url: the url of the master to which this slave should attach
        :type master_url: string | None
        :param num_executors: the number of executors the slave service should use
        :type num_executors: int | None
        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param eventlog_file: an optional alternate file in which to write event logs
        :type eventlog_file: str | None
        """
        num_executors = num_executors or Configuration['num_executors']
        master_url = master_url or '{}:{}'.format(Configuration['master_hostname'], Configuration['master_port'])
        port = port or Configuration['port']
        log_level = log_level or Configuration['log_level']
        eventlog_file = eventlog_file or Configuration['eventlog_file']

        log.configure_logging(log_level=log_level, log_file=Configuration['log_file'].format(port))
        analytics.initialize(eventlog_file)
        analytics.record_event(analytics.SERVICE_STARTED, service='slave')

        cluster_slave = ClusterSlave(
            port=port,
            num_executors=num_executors,
            host=Configuration['hostname'],
        )
        application = ClusterSlaveApplication(cluster_slave)

        ioloop = self._start_application(application, port)

        self._write_pid_file(Configuration['slave_pid_file'])

        # connect to master once tornado ioloop is running
        connect_slave_to_master = functools.partial(cluster_slave.connect_to_master, master_url=master_url)
        ioloop.add_callback(connect_slave_to_master)

        ioloop.start()  # this call blocks until the server is stopped
        ioloop.close(all_fds=True)  # all_fds=True is necessary here to make sure connections don't hang
        self._logger.notice('Slave server was stopped.')
