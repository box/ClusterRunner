import requests

from contextlib import suppress
import functools
import os
from os.path import dirname, join, realpath
from subprocess import DEVNULL, Popen
import sys
import shutil
import tempfile

from app.client.cluster_api_client import ClusterMasterAPIClient, ClusterSlaveAPIClient
from app.util import log, poll, process_utils
from app.util.conf.base_config_loader import BASE_CONFIG_FILE_SECTION
from app.util.conf.config_file import ConfigFile
from app.util.secret import Secret


class FunctionalTestCluster(object):
    """
    This class can create and destroy local clusters consisting of a single master and multiple slave services. It also
    provides methods to introspect into the state of the services. This is used for functional tests.
    """
    _MASTER_PORT = 43000
    _SLAVE_START_PORT = 43001

    def __init__(self, verbose=False):
        """
        :param verbose: If true, output from the master and slave processes is allowed to pass through to stdout.
        :type verbose: bool
        """
        self._verbose = verbose
        self._logger = log.get_logger(__name__)

        self.master = None
        self.slaves = []

        self._master_eventlog_name = None
        self._slave_eventlog_names = []
        self._next_slave_port = self._SLAVE_START_PORT

        self._clusterrunner_repo_dir = dirname(dirname(dirname(dirname(realpath(__file__)))))
        self._app_executable = join(self._clusterrunner_repo_dir, 'main.py')

        self._master_app_base_dir = None
        self._slaves_app_base_dirs = []

    @property
    def master_app_base_dir(self):
        return self._master_app_base_dir

    @property
    def slaves_app_base_dirs(self):
        return self._slaves_app_base_dirs

    def _create_test_config_file(self, base_dir_sys_path):
        """
        Create a temporary conf file just for this test.

        :param base_dir_sys_path: Sys path of the base app dir
        :type base_dir_sys_path: unicode

        :return: The path to the conf file
        :rtype: str
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
        }
        for conf_key, conf_value in conf_values_to_set.items():
            conf_file.write_value(conf_key, conf_value, BASE_CONFIG_FILE_SECTION)

        return test_conf_file_path

    def start_master(self):
        """
        Start a master service for this cluster.

        :return: An API client object through which API calls to the master can be made
        :rtype: ClusterMasterAPIClient
        """
        self._start_master_process()
        return self.master_api_client

    def start_slaves(self, num_slaves, num_executors_per_slave=1, start_port=None):
        """
        Start slave services for this cluster.

        :param num_slaves: The number of slave services to start
        :type num_slaves: int
        :param num_executors_per_slave: The number of executors that each slave will be configured to use
        :type num_executors_per_slave: int
        :param start_port: The port number of the first slave to launch. If None, default to the current counter.
            Subsequent slaves will be started on subsequent port numbers.
        :type start_port: int | None
        :return: A list of API client objects through which API calls to each slave can be made
        :rtype: list[ClusterSlaveAPIClient]
        """
        new_slaves = self._start_slave_processes(num_slaves, num_executors_per_slave, start_port)
        return [ClusterSlaveAPIClient(base_api_url=slave.url) for slave in new_slaves]

    def start_slave(self, **kwargs):
        """
        Start a slave service for this cluster. (This is a convenience method equivalent to `start_slaves(1)`.)

        :return: An API client object through which API calls to the slave can be made
        :rtype: ClusterSlaveAPIClient
        """
        return self.start_slaves(num_slaves=1, **kwargs)[0]

    @property
    def master_api_client(self):
        return ClusterMasterAPIClient(base_api_url=self.master.url)

    @property
    def slave_api_clients(self):
        return [ClusterSlaveAPIClient(base_api_url=slave.url) for slave in self.slaves]

    def _start_master_process(self):
        """
        Start the master process on localhost.

        :return: A ClusterController object which wraps the master service's Popen instance
        :rtype: ClusterController
        """
        if self.master:
            raise RuntimeError('Master service was already started for this cluster.')

        popen_kwargs = {}
        if not self._verbose:
            popen_kwargs.update({'stdout': DEVNULL, 'stderr': DEVNULL})  # hide output of master process

        self._master_eventlog_name = tempfile.NamedTemporaryFile(delete=False).name
        self._master_app_base_dir = tempfile.TemporaryDirectory()
        master_config_file_path = self._create_test_config_file(self._master_app_base_dir.name)
        master_hostname = 'localhost'
        master_cmd = [
            sys.executable,
            self._app_executable,
            'master',
            '--port', str(self._MASTER_PORT),
            '--eventlog-file', self._master_eventlog_name,
            '--config-file', master_config_file_path,
        ]

        # Don't use shell=True in the Popen here; the kill command might only kill "sh -c", not the actual process.
        self.master = ClusterController(
            Popen(master_cmd, **popen_kwargs),
            host=master_hostname,
            port=self._MASTER_PORT,
        )
        self._block_until_master_ready()  # wait for master to start up
        return self.master

    def _block_until_master_ready(self, timeout=10):
        """
        Blocks until the master is ready and responsive. Repeatedly sends a GET request to the master until the
        master responds. If the master is not responsive within the timeout, raise an exception.

        :param timeout: Max number of seconds to wait before raising an exception
        :type timeout: int
        """
        is_master_ready = functools.partial(self._is_url_responsive, self.master.url)
        master_is_ready = poll.wait_for(is_master_ready, timeout_seconds=timeout)
        if not master_is_ready:
            raise TestClusterTimeoutError('Master service did not start up before timeout.')

    def _start_slave_processes(self, num_slaves, num_executors_per_slave, start_port=None):
        """
        Start the slave processes on localhost.

        :param num_slaves: The number of slave processes to start
        :type num_slaves: int
        :param num_executors_per_slave: The number of executors to start each slave with
        :type num_executors_per_slave: int
        :param start_port: The port number of the first slave to launch. If None, default to the current counter.
            Subsequent slaves will be started on subsequent port numbers.
        :type start_port: int | None
        :return: A list of ClusterController objects which wrap the slave services' Popen instances
        :rtype: list[ClusterController]
        """
        popen_kwargs = {}
        if not self._verbose:
            popen_kwargs.update({'stdout': DEVNULL, 'stderr': DEVNULL})  # hide output of slave process

        if start_port is not None:
            self._next_slave_port = start_port

        slave_hostname = 'localhost'
        new_slaves = []
        for _ in range(num_slaves):
            slave_port = self._next_slave_port
            self._next_slave_port += 1

            slave_eventlog = tempfile.NamedTemporaryFile().name  # each slave writes to its own file to avoid collision
            self._slave_eventlog_names.append(slave_eventlog)
            slave_base_app_dir = tempfile.TemporaryDirectory()
            self._slaves_app_base_dirs.append(slave_base_app_dir)
            slave_config_file_path = self._create_test_config_file(slave_base_app_dir.name)

            slave_cmd = [
                sys.executable,
                self._app_executable,
                'slave',
                '--port', str(slave_port),
                '--num-executors', str(num_executors_per_slave),
                '--master-url', '{}:{}'.format(self.master.host, self.master.port),
                '--eventlog-file', slave_eventlog,
                '--config-file', slave_config_file_path,
            ]

            # Don't use shell=True in the Popen here; the kill command may only kill "sh -c", not the actual process.
            new_slaves.append(ClusterController(
                Popen(slave_cmd, **popen_kwargs),
                host=slave_hostname,
                port=slave_port,
            ))

        self.slaves.extend(new_slaves)
        self._block_until_slaves_ready()
        return new_slaves

    def _block_until_slaves_ready(self, timeout=15):
        """
        Blocks until all slaves are ready and responsive. Repeatedly sends a GET request to each slave in turn until
        the slave responds. If all slaves do not become responsive within the timeout, raise an exception.

        :param timeout: Max number of seconds to wait before raising an exception
        :type timeout: int
        """
        slaves_to_check = self.slaves.copy()  # we'll remove slaves from this list as they become ready

        def are_all_slaves_ready():
            for slave in slaves_to_check.copy():  # copy list so we can modify the original list inside the loop
                if self._is_url_responsive(slave.url):
                    slaves_to_check.remove(slave)
                else:
                    return False
            return True

        all_slaves_are_ready = poll.wait_for(are_all_slaves_ready, timeout_seconds=timeout)
        num_slaves = len(self.slaves)
        num_ready_slaves = num_slaves - len(slaves_to_check)
        if not all_slaves_are_ready:
            raise TestClusterTimeoutError('All slaves did not start up before timeout. '
                                          '{} of {} started successfully.'.format(num_ready_slaves, num_slaves))

    def _is_url_responsive(self, url):
        is_responsive = False
        with suppress(requests.ConnectionError):
            resp = requests.get(url)
            if resp and resp.ok:
                is_responsive = True

        return is_responsive

    def block_until_build_queue_empty(self, timeout=15):
        """
        This blocks until the master's build queue is empty. This data is exposed via the /queue endpoint and contains
        any jobs that are currently building or not yet started. If the queue is not empty before the timeout, this
        method raises an exception.

        :param timeout: The maximum number of seconds to block before raising an exception.
        :type timeout: int
        """
        if self.master is None:
            return

        def is_queue_empty():
            queue_resp = requests.get('{}/v1/queue'.format(self.master.url))
            if queue_resp and queue_resp.ok:
                queue_data = queue_resp.json()
                if len(queue_data['queue']) == 0:
                    return True  # queue is empty, so master must be idle
            self._logger.info('Waiting on build queue to become empty.')
            return False

        queue_is_empty = poll.wait_for(is_queue_empty, timeout_seconds=timeout, poll_period=1,
                                       exceptions_to_swallow=(requests.ConnectionError, ValueError))
        if not queue_is_empty:
            self._logger.error('Master queue did not become empty before timeout.')
            raise TestClusterTimeoutError('Master queue did not become empty before timeout.')

    def kill_master(self):
        """
        Kill the master process and return an object wrapping the return code, stdout, and stderr.

        :return: The killed master service with return code, stdout, and stderr set.
        :rtype: ClusterController
        """
        if self.master:
            self.master.kill()

        master, self.master = self.master, None
        return master

    def kill_slaves(self, kill_gracefully=True):
        """
        Kill all the slave processes and return objects wrapping the return code, stdout, and stderr of each process.

        :param kill_gracefully: If True do a gracefull kill (sigterm), else do a sigkill
        :type kill_gracefully: bool
        :return: The killed slave services with return code, stdout, and stderr set.
        :rtype: list[ClusterController]
        """
        for service in self.slaves:
            if service:
                service.kill(kill_gracefully)

        slaves, self.slaves = self.slaves, []
        return slaves

    def kill(self):
        """
        Kill the master and all the slave subprocesses.

        :return: The killed master and killed slave services with return code, stdout, and stderr set.
        :rtype: list[ClusterController]
        """
        services = [self.kill_master()]
        services.extend(self.kill_slaves())
        services = [service for service in services if service is not None]  # remove `None` values from list
        return services

    def block_until_n_slaves_dead(self, num_slaves, timeout):

        def are_n_slaves_dead(n):
            dead_slaves = [slave for slave in self.slaves if not slave.is_alive()]
            return len(dead_slaves) == n

        def are_slaves_dead():
            are_n_slaves_dead(num_slaves)

        slaves_died_within_timeout = poll.wait_for(are_slaves_dead, timeout_seconds=timeout)
        return slaves_died_within_timeout


class ClusterController(object):
    """
    A data container that wraps a process and holds metadata about that process. This is useful for wrapping up data
    relating to the various services started by the FunctionalTestCluster (master, slaves, etc.).
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
        return 'http://{}:{}'.format(self.host, self.port)

    def is_alive(self):
        return self.process.poll() is None


class TestClusterTimeoutError(Exception):
    """
    This represents a timeout occurring during an operation on the test Cluster.
    """
