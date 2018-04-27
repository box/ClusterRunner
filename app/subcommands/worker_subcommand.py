import functools

from app.worker.cluster_worker import ClusterWorker
from app.subcommands.service_subcommand import ServiceSubcommand
from app.util import analytics, log
from app.util.conf.configuration import Configuration
from app.web_framework.cluster_worker_application import ClusterWorkerApplication


class WorkerSubcommand(ServiceSubcommand):
    _THREAD_NAME = 'WorkerTornadoThread'

    def async_run(self, port, manager_url, num_executors, log_level, eventlog_file):
        """
        Run a ClusterRunner worker service.

        :param port: the port on which to run the worker service
        :type port: int | None
        :param manager_url: the url of the manager to which this worker should attach
        :type manager_url: string | None
        :param num_executors: the number of executors the worker service should use
        :type num_executors: int | None
        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param eventlog_file: an optional alternate file in which to write event logs
        :type eventlog_file: str | None
        """
        num_executors = num_executors or Configuration['num_executors']
        manager_url = manager_url or '{}:{}'.format(Configuration['manager_hostname'], Configuration['manager_port'])
        port = port or Configuration['port']
        log_level = log_level or Configuration['log_level']
        eventlog_file = eventlog_file or Configuration['eventlog_file']

        log.configure_logging(log_level=log_level, log_file=Configuration['log_file'].format(port))
        analytics.initialize(eventlog_file)
        analytics.record_event(analytics.SERVICE_STARTED, service='worker')

        cluster_worker = ClusterWorker(
            port=port,
            num_executors=num_executors,
            host=Configuration['hostname'],
        )

        application = ClusterWorkerApplication(cluster_worker)

        ioloop = self._start_application(application, port)

        self._write_pid_file(Configuration['worker_pid_file'])

        # connect to manager once tornado ioloop is running
        connect_worker_to_manager = functools.partial(cluster_worker.connect_to_manager, manager_url=manager_url)
        ioloop.add_callback(connect_worker_to_manager)

        # start sending heartbeat after connecting to manager
        start_worker_heartbeat = functools.partial(cluster_worker.start_heartbeat_thread)
        ioloop.add_callback(start_worker_heartbeat)

        ioloop.start()  # this call blocks until the server is stopped
        ioloop.close(all_fds=True)  # all_fds=True is necessary here to make sure connections don't hang
        self._logger.notice('Worker server was stopped.')
