from contextlib import suppress
import functools
import os
from os.path import dirname, join, realpath
from pprint import pformat
from subprocess import DEVNULL, Popen
import sys
import shutil
import tempfile

import requests

from app.client.cluster_api_client import ClusterManagerAPIClient, ClusterWorkerAPIClient
from app.util import log, poll, process_utils
from app.util.conf.base_config_loader import BASE_CONFIG_FILE_SECTION
from app.util.conf.config_file import ConfigFile
from app.util.conf.configuration import Configuration
from app.util.secret import Secret


class FunctionalTestCluster(object):
    """
    This class can create and destroy local clusters consisting of a single manager and multiple worker services. It also
    provides methods to introspect into the state of the services. This is used for functional tests.
    """
    _MASTER_PORT = 43000
    _SLAVE_START_PORT = 43001

    def __init__(self, verbose=False):
        """
        :param verbose: If true, output from the manager and worker processes is allowed to pass through to stdout.
        :type verbose: bool
        """
        self._verbose = verbose
        self._logger = log.get_logger(__name__)

        self.manager = None
        self.workers = []

        self._manager_eventlog_name = None
        self._worker_eventlog_names = []
        self._next_worker_port = self._SLAVE_START_PORT

        self._clusterrunner_repo_dir = dirname(dirname(dirname(dirname(realpath(__file__)))))
        self._app_executable = [sys.executable, '-m', 'app']

        self._manager_app_base_dir = None
        self._workers_app_base_dirs = []

    @property
    def manager_app_base_dir(self):
        return self._manager_app_base_dir

    @property
    def workers_app_base_dirs(self):
        return self._workers_app_base_dirs

    def _create_test_config_file(self, base_dir_sys_path: str, **extra_conf_vals) -> str:
        """
        Create a temporary conf file just for this test.

        :param base_dir_sys_path: Sys path of the base app dir
        :param extra_conf_vals: Optional; additional values to set in the conf file
        :return: The path to the conf file
        """
        # Copy default conf file to tmp location
        self._conf_template_path = join(self._clusterrunner_repo_dir, 'conf', 'default_clusterrunner.conf')
        # Create the conf file inside base dir so we can clean up the test at the end just by removing the base dir
        test_conf_file_path = tempfile.NamedTemporaryFile(dir=base_dir_sys_path).name
        shutil.copy(self._conf_template_path, test_conf_file_path)
        os.chmod(test_conf_file_path, ConfigFile.CONFIG_FILE_MODE)
        conf_file = ConfigFile(test_conf_file_path)

        # Set custom conf file values for this test
        conf_values_to_set = {
            'secret': Secret.get(),
            'base_directory': base_dir_sys_path,
            'max_log_file_size': 1024 * 5,
            'hostname': 'localhost',  # Ensure the worker is reachable by manager.
        }
        conf_values_to_set.update(extra_conf_vals)
        for conf_key, conf_value in conf_values_to_set.items():
            conf_file.write_value(conf_key, conf_value, BASE_CONFIG_FILE_SECTION)

        return test_conf_file_path

    def start_manager(self, **extra_conf_vals) -> ClusterManagerAPIClient:
        """
        Start a manager service for this cluster.
        :param extra_conf_vals: Optional; additional values to set in the manager service conf file
        :return: An API client object through which API calls to the manager can be made
        """
        self._start_manager_process(**extra_conf_vals)
        return self.manager_api_client

    def start_workers(self, num_workers, num_executors_per_worker=1, start_port=None, **extra_conf_vals):
        """
        Start worker services for this cluster.

        :param num_workers: The number of worker services to start
        :type num_workers: int
        :param num_executors_per_worker: The number of executors that each worker will be configured to use
        :type num_executors_per_worker: int
        :param start_port: The port number of the first worker to launch. If None, default to the current counter.
            Subsequent workers will be started on subsequent port numbers.
        :type start_port: int | None
        :return: A list of API client objects through which API calls to each worker can be made
        :rtype: list[ClusterWorkerAPIClient]
        """
        new_workers = self._start_worker_processes(num_workers, num_executors_per_worker, start_port, **extra_conf_vals)
        return [ClusterWorkerAPIClient(base_api_url=worker.url) for worker in new_workers]

    def start_worker(self, **kwargs):
        """
        Start a worker service for this cluster. (This is a convenience method equivalent to `start_workers(1)`.)

        :return: An API client object through which API calls to the worker can be made
        :rtype: ClusterWorkerAPIClient
        """
        return self.start_workers(num_workers=1, **kwargs)[0]

    @property
    def manager_api_client(self):
        return ClusterManagerAPIClient(base_api_url=self.manager.url)

    @property
    def worker_api_clients(self):
        return [ClusterWorkerAPIClient(base_api_url=worker.url) for worker in self.workers]

    def _start_manager_process(self, **extra_conf_vals) -> 'ClusterController':
        """
        Start the manager process on localhost.
        :param extra_conf_vals: Optional; additional values to set in the manager service conf file
        :return: A ClusterController object which wraps the manager service's Popen instance
        """
        if self.manager:
            raise RuntimeError('Manager service was already started for this cluster.')

        popen_kwargs = {}
        if not self._verbose:
            popen_kwargs.update({'stdout': DEVNULL, 'stderr': DEVNULL})  # hide output of manager process

        self._manager_eventlog_name = tempfile.NamedTemporaryFile(delete=False).name
        self._manager_app_base_dir = tempfile.TemporaryDirectory()
        manager_config_file_path = self._create_test_config_file(self._manager_app_base_dir.name, **extra_conf_vals)
        manager_hostname = 'localhost'
        manager_cmd = self._app_executable + [
            'manager',
            '--port', str(self._MASTER_PORT),
            '--eventlog-file', self._manager_eventlog_name,
            '--config-file', manager_config_file_path,
        ]

        # Don't use shell=True in the Popen here; the kill command might only kill "sh -c", not the actual process.
        self.manager = ClusterController(
            Popen(manager_cmd, **popen_kwargs),
            host=manager_hostname,
            port=self._MASTER_PORT,
        )
        self._block_until_manager_ready()  # wait for manager to start up
        return self.manager

    def _block_until_manager_ready(self, timeout=10):
        """
        Blocks until the manager is ready and responsive. Repeatedly sends a GET request to the manager until the
        manager responds. If the manager is not responsive within the timeout, raise an exception.

        :param timeout: Max number of seconds to wait before raising an exception
        :type timeout: int
        """
        is_manager_ready = functools.partial(self._is_url_responsive, self.manager.url)
        manager_is_ready = poll.wait_for(is_manager_ready, timeout_seconds=timeout)
        if not manager_is_ready:
            raise TestClusterTimeoutError('Manager service did not start up before timeout.')

    def _start_worker_processes(self, num_workers, num_executors_per_worker, start_port=None, **extra_conf_vals):
        """
        Start the worker processes on localhost.

        :param num_workers: The number of worker processes to start
        :type num_workers: int
        :param num_executors_per_worker: The number of executors to start each worker with
        :type num_executors_per_worker: int
        :param start_port: The port number of the first worker to launch. If None, default to the current counter.
            Subsequent workers will be started on subsequent port numbers.
        :type start_port: int | None
        :return: A list of ClusterController objects which wrap the worker services' Popen instances
        :rtype: list[ClusterController]
        """
        popen_kwargs = {}
        if not self._verbose:
            popen_kwargs.update({'stdout': DEVNULL, 'stderr': DEVNULL})  # hide output of worker process

        if start_port is not None:
            self._next_worker_port = start_port

        worker_hostname = 'localhost'
        new_workers = []
        for _ in range(num_workers):
            worker_port = self._next_worker_port
            self._next_worker_port += 1

            worker_eventlog = tempfile.NamedTemporaryFile().name  # each worker writes to its own file to avoid collision
            self._worker_eventlog_names.append(worker_eventlog)
            worker_base_app_dir = tempfile.TemporaryDirectory()
            self._workers_app_base_dirs.append(worker_base_app_dir)

            worker_config_file_path = self._create_test_config_file(worker_base_app_dir.name, **extra_conf_vals)

            worker_cmd = self._app_executable + [
                'worker',
                '--port', str(worker_port),
                '--num-executors', str(num_executors_per_worker),
                '--manager-url', '{}:{}'.format(self.manager.host, self.manager.port),
                '--eventlog-file', worker_eventlog,
                '--config-file', worker_config_file_path,
            ]

            # Don't use shell=True in the Popen here; the kill command may only kill "sh -c", not the actual process.
            new_workers.append(ClusterController(
                Popen(worker_cmd, **popen_kwargs),
                host=worker_hostname,
                port=worker_port,
            ))

        self.workers.extend(new_workers)
        self._block_until_workers_ready()
        return new_workers

    def _block_until_workers_ready(self, timeout=15):
        """
        Blocks until all workers are ready and responsive. Repeatedly sends a GET request to each worker in turn until
        the worker responds. If all workers do not become responsive within the timeout, raise an exception.

        :param timeout: Max number of seconds to wait before raising an exception
        :type timeout: int
        """
        workers_to_check = self.workers.copy()  # we'll remove workers from this list as they become ready

        def are_all_workers_ready():
            for worker in workers_to_check.copy():  # copy list so we can modify the original list inside the loop
                if self._is_url_responsive(worker.url):
                    workers_to_check.remove(worker)
                else:
                    return False
            return True

        all_workers_are_ready = poll.wait_for(are_all_workers_ready, timeout_seconds=timeout)
        num_workers = len(self.workers)
        num_ready_workers = num_workers - len(workers_to_check)
        if not all_workers_are_ready:
            raise TestClusterTimeoutError('All workers did not start up before timeout. '
                                          '{} of {} started successfully.'.format(num_ready_workers, num_workers))

    def _is_url_responsive(self, url):
        is_responsive = False
        with suppress(requests.ConnectionError):
            resp = requests.get(url)
            if resp and resp.ok:
                is_responsive = True

        return is_responsive

    def block_until_build_queue_empty(self, timeout=15):
        """
        This blocks until the manager's build queue is empty. This data is exposed via the /queue endpoint and contains
        any jobs that are currently building or not yet started. If the queue is not empty before the timeout, this
        method raises an exception.

        :param timeout: The maximum number of seconds to block before raising an exception.
        :type timeout: int
        """
        if self.manager is None:
            return

        def is_queue_empty():
            nonlocal queue_data
            queue_resp = requests.get('{}/v1/queue'.format(self.manager.url))
            if queue_resp and queue_resp.ok:
                queue_data = queue_resp.json()
                if len(queue_data['queue']) == 0:
                    return True  # queue is empty, so manager must be idle
            self._logger.info('Waiting on build queue to become empty.')
            return False

        queue_data = None
        queue_is_empty = poll.wait_for(is_queue_empty, timeout_seconds=timeout, poll_period=1,
                                       exceptions_to_swallow=(requests.ConnectionError, ValueError))
        if not queue_is_empty:
            self._logger.error('Manager queue did not become empty before timeout. '
                               'Last queue response: {}'.format(pformat(queue_data)))
            raise TestClusterTimeoutError('Manager queue did not become empty before timeout.')

    def kill_manager(self):
        """
        Kill the manager process and return an object wrapping the return code, stdout, and stderr.

        :return: The killed manager service with return code, stdout, and stderr set.
        :rtype: ClusterController
        """
        if self.manager:
            self.manager.kill()

        manager, self.manager = self.manager, None
        return manager

    def kill_workers(self, kill_gracefully=True):
        """
        Kill all the worker processes and return objects wrapping the return code, stdout, and stderr of each process.

        :param kill_gracefully: If True do a gracefull kill (sigterm), else do a sigkill
        :type kill_gracefully: bool
        :return: The killed worker services with return code, stdout, and stderr set.
        :rtype: list[ClusterController]
        """
        for service in self.workers:
            if service:
                service.kill(kill_gracefully)

        workers, self.workers = self.workers, []
        return workers

    def kill(self):
        """
        Kill the manager and all the worker subprocesses.

        :return: The killed manager and killed worker services with return code, stdout, and stderr set.
        :rtype: list[ClusterController]
        """
        services = [self.kill_manager()]
        services.extend(self.kill_workers())
        services = [service for service in services if service is not None]  # remove `None` values from list
        return services

    def block_until_n_workers_marked_dead_in_manager(self, num_workers, timeout):
        def are_n_workers_marked_dead_in_manager(n):
            workers_marked_dead = [worker for worker in self.manager_api_client.get_workers().values()
                                  if isinstance(worker, list) and not worker[0].get('is_alive')]
            return len(workers_marked_dead) == n

        def are_workers_marked_dead_in_manager():
            are_n_workers_marked_dead_in_manager(num_workers)

        workers_marked_dead_within_timeout = poll.wait_for(are_workers_marked_dead_in_manager, timeout_seconds=timeout)
        return workers_marked_dead_within_timeout

    def block_until_n_workers_dead(self, num_workers, timeout):

        def are_n_workers_dead(n):
            dead_workers = [worker for worker in self.workers if not worker.is_alive()]
            return len(dead_workers) == n

        def are_workers_dead():
            are_n_workers_dead(num_workers)

        workers_died_within_timeout = poll.wait_for(are_workers_dead, timeout_seconds=timeout)
        return workers_died_within_timeout


class ClusterController(object):
    """
    A data container that wraps a process and holds metadata about that process. This is useful for wrapping up data
    relating to the various services started by the FunctionalTestCluster (manager, workers, etc.).
    """
    def __init__(self, process, host, port):
        """
        :param process: The Popen process instance of the associated service
        :type process: Popen
        :param host: The service host (e.g., 'localhost')
        :type host: str
        :param port: The service port (e.g., 43000)
        :type port: int
        """
        self.process = process
        self.host = host
        self.port = port

        self.return_code = None
        self.stdout = None
        self.stderr = None

        self._logger = log.get_logger(__name__)

    def kill(self, kill_gracefully=True):
        """
        Kill the underlying process for this service object and set the return code and output.

        :param kill_gracefully: If True do a gracefull kill (sigterm), else do a sigkill
        :type kill_gracefully: bool
        :return: The return code, stdout, and stderr of the process
        :rtype: (int, str, str)
        """
        if kill_gracefully:
            self._logger.notice('Gracefully killing process with pid {}...'.format(self.process.pid))
            output = process_utils.kill_gracefully(self.process, timeout=15)
        else:
            self._logger.notice('Hard killing process with pid {}...'.format(self.process.pid))
            output = process_utils.kill_hard(self.process)

        self.return_code, self.stdout, self.stderr = output
        return self.return_code, self.stdout, self.stderr

    @property
    def url(self):
        return '{}://{}:{}'.format(Configuration['protocol_scheme'], self.host, self.port)

    def is_alive(self):
        return self.process.poll() is None


class TestClusterTimeoutError(Exception):
    """
    This represents a timeout occurring during an operation on the test Cluster.
    """
