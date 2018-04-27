import getpass
from multiprocessing.dummy import Pool
import os
from os.path import join
import sys
from urllib.parse import urlparse

import requests

from app.client.build_runner import BuildRunner
from app.deployment.deploy_target import DeployTarget
from app.deployment.remote_manager_service import RemoteManagerService
from app.deployment.remote_worker_service import RemoteWorkerService
from app.subcommands.subcommand import Subcommand
from app.util.poll import wait_for
from app.util import fs, log
from app.util.conf.configuration import Configuration
from app.util.conf.manager_config_loader import ManagerConfigLoader
from app.util.conf.worker_config_loader import WorkerConfigLoader
from app.util.network import Network
from app.util.url_builder import UrlBuilder


class DeploySubcommand(Subcommand):
    _logger = log.get_logger(__name__)
    # Number of seconds to wait for all of the worker services to successfully register with the manager service
    _SLAVE_REGISTRY_TIMEOUT_SEC = 5

    def run(self, log_level, manager, manager_port, workers, worker_port, num_executors):
        """
        'Deploy' can be a vague word, so we should be specific about what this command accomplishes.

        This command will:
        - Replace the existing binary files in the workers and manager hosts with the binary files running this
          command currently. If there is nothing to replace, this command will just place the binary files there.
        - Stop all clusterrunner services running on all workers and the manager.
        - Start the manager and worker services on the manager and worker hosts.
        - Poll until timeout to validate that the manager service has started, and that the workers have successfully
          connected with the manager.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param manager: the manager hostname (no port) to deploy the manager service to
        :type manager: str | None
        :param manager_port: the port number the manager service will listen on
        :type manager_port: int | None
        :param workers: list of worker hostnames (no ports) to deploy the worker service to
        :type workers: [str] | None
        :param worker_port: the port number the worker services will listen on
        :type worker_port: int | None
        :param num_executors: the number of executors that will be run per worker
        :type num_executors: int | None
        """
        log.configure_logging(
            log_level=log_level or Configuration['log_level'],
            log_file=Configuration['log_file'],
            simplified_console_logs=True,
        )
        conf_path = Configuration['config_file']
        current_executable = sys.executable
        username = getpass.getuser()
        worker_config = self._get_loaded_config(conf_path, WorkerConfigLoader())
        manager_config = self._get_loaded_config(conf_path, ManagerConfigLoader())
        manager = manager or worker_config.get('manager_hostname')
        manager_port = manager_port or manager_config.get('port')
        workers = workers or manager_config.get('workers')
        worker_port = worker_port or worker_config.get('port')
        num_executors = num_executors or worker_config.get('num_executors')
        clusterrunner_executable_dir = join(os.path.expanduser('~'), '.clusterrunner', 'dist')
        clusterrunner_executable = join(clusterrunner_executable_dir, 'clusterrunner')

        self._logger.info('Compressing binaries...')
        binaries_tar_path = self._binaries_tar(current_executable, Configuration['root_directory'])

        self._logger.info('Deploying binaries and confs on manager and workers...')
        arguments = [[host, username, current_executable, binaries_tar_path, conf_path] for host in workers + [manager]]
        Pool().starmap(self._deploy_binaries_and_conf, arguments)

        self._logger.info('Stopping and starting all clusterrunner services...')
        self._start_services(manager, manager_port, workers, worker_port, num_executors, username, clusterrunner_executable)

        self._logger.info('Validating successful deployment...')
        manager_service_url = '{}:{}'.format(manager, manager_port)
        self._validate_successful_deployment(manager_service_url, workers)

        self._logger.info('Deploy SUCCESS to workers: {}'.format(','.join(workers)))

    def _binaries_tar(self, current_executable, clusterrunner_bin_dir):
        """
        Return a tgz of the binaries directory for the currently running ClusterRunner process.

        Throws an exception if the current process if running from source.

        :param current_executable: path to the executable (ie: /usr/bin/python, ./clusterrunner, etc)
        :type current_executable: str
        :param clusterrunner_bin_dir: path to the directory containing the bin/source files of ClusterRunner
        :type clusterrunner_bin_dir: str
        :return: the path to the tar file containing all of the ClusterRunner binaries
        :rtype: str
        """
        # We don't support 'clusterrunner deploy' from source yet. @TODO: support this feature
        if 'python' in current_executable:
            self._logger.error('sys.executable is set to {}. Cannot deploy from source.'.format(current_executable))
            raise SystemExit(1)

        tar_file_path = join(clusterrunner_bin_dir, 'clusterrunner.tgz')

        if os.path.isfile(tar_file_path):
            self._logger.info('Compressed tar file {} already exists, skipping compression.'.format(tar_file_path))
            return tar_file_path

        fs.tar_directory(clusterrunner_bin_dir, tar_file_path)
        return tar_file_path

    def _deploy_binaries_and_conf(self, host, username, current_executable, binaries_tar_path, in_use_conf_path):
        """
        Move binaries and conf to single host.

        :param host: host to deploy to
        :type host: str
        :param username: current username
        :param current_executable: path to the executable (ie: /usr/bin/python, ./clusterrunner, etc)
        :type current_executable: str
        :param binaries_tar_path: path to tar.gz file of clusterrunner binaries
        :type binaries_tar_path: str
        :param in_use_conf_path: path toe currently used conf file
        :type in_use_conf_path: str
        """
        clusterrunner_dir = join(os.path.expanduser('~'), '.clusterrunner')
        clusterrunner_executable_dir = join(clusterrunner_dir, 'dist')
        clusterrunner_executable_deploy_target = join(clusterrunner_executable_dir, 'clusterrunner')
        clusterrunner_conf_deploy_target = join(clusterrunner_dir, 'clusterrunner.conf')
        deploy_target = DeployTarget(host, username)

        if Network.are_hosts_same(host, 'localhost'):
            # Do not want to overwrite the currently running executable.
            if current_executable != clusterrunner_executable_deploy_target:
                deploy_target.deploy_binary(binaries_tar_path, clusterrunner_executable_dir)

            # Do not want to overwrite the currently used conf.
            if in_use_conf_path != clusterrunner_conf_deploy_target:
                deploy_target.deploy_conf(in_use_conf_path, clusterrunner_conf_deploy_target)
        else:
            deploy_target.deploy_binary(binaries_tar_path, clusterrunner_executable_dir)
            deploy_target.deploy_conf(in_use_conf_path, clusterrunner_conf_deploy_target)

    def _start_services(self, manager, manager_port, workers, worker_port, num_executors, username, clusterrunner_executable):
        """
        Stop and start the appropriate clusterrunner services on all machines.

        :param manager: manager hostnames
        :type manager: str
        :param manager_port: manager's port
        :type manager_port: int
        :param workers: worker hostnames
        :type workers: list[str]
        :param worker_port: worker's port
        :type worker_port: int
        :param num_executors: number of concurrent executors
        :type num_executors: int
        :param username: current username
        :type username: str
        :param clusterrunner_executable: where the clusterrunner executable on the remote hosts is expected to be
        :type clusterrunner_executable: str
        """
        # We want to stop worker services before the manager service, as that is a more graceful shutdown and also
        # reduces the risk of a race condition where the worker service sends a worker-shutdown request to the manager
        # after the new manager service starts.
        self._logger.debug('Stopping all worker services')
        worker_services = [RemoteWorkerService(worker, username, clusterrunner_executable) for worker in workers]
        Pool().map(lambda worker_service: worker_service.stop(), worker_services)

        self._logger.debug('Stopping manager service on {}...'.format(manager))
        manager_service = RemoteManagerService(manager, username, clusterrunner_executable)
        manager_service.stop()

        self._logger.debug('Starting manager service on {}:{}'.format(manager_service.host, manager_port))
        manager_service.start_and_block_until_up(manager_port)

        self._logger.debug('Starting worker services')

        for worker_service in worker_services:
            try:
                worker_service.start(manager, manager_port, worker_port, num_executors)
            except Exception as e:  # pylint: disable=broad-except
                self._logger.error('Failed to start worker service on {} with message: {}'.format(worker_service.host, e))

    def _validate_successful_deployment(self, manager_service_url, workers_to_validate):
        """
        Poll the manager's /workers endpoint until either timeout or until all of the workers have registered with
        the manager.

        Throws exception upon timeout or API response error.

        :param manager_service_url: the hostname:port for the running manager service
        :type manager_service_url: str
        :param workers_to_validate: the list of worker hostnames (no ports) to deploy to
        :type workers_to_validate: list[str]
        """
        manager_api = UrlBuilder(manager_service_url, BuildRunner.API_VERSION)
        worker_api_url = manager_api.url('worker')
        network = Network()

        def all_workers_registered():
            registered_worker_uids = set(
                [Network.get_host_id(x) for x in self._registered_worker_hostnames(worker_api_url, network)]
            )
            workers_to_validate_uids = set(
                [Network.get_host_id(x) for x in workers_to_validate]
            )
            return registered_worker_uids == workers_to_validate_uids

        if not wait_for(
                boolean_predicate=all_workers_registered,
                timeout_seconds=self._SLAVE_REGISTRY_TIMEOUT_SEC,
                poll_period=1,
                exceptions_to_swallow=(requests.RequestException, requests.ConnectionError)
        ):
            try:
                registered_workers = self._registered_worker_hostnames(worker_api_url, network)
                non_registered_workers = self._non_registered_workers(registered_workers, workers_to_validate)
            except ConnectionError:
                self._logger.error('Error contacting {} on the manager.'.format(worker_api_url))
                raise SystemExit(1)

            self._logger.error('Worker registration timed out after {} sec, with workers {} missing.'.format(
                self._SLAVE_REGISTRY_TIMEOUT_SEC, ','.join(non_registered_workers)))
            raise SystemExit(1)

    def _registered_worker_hostnames(self, worker_api_url, network):
        """
        Return list of worker hosts that have registered with the manager service.

        :param worker_api_url: url to the manager's '/worker' endpoint
        :type worker_api_url: str
        :param network: the Network instance (so that we don't have to reinstantiate it many times)
        :type network: Network
        :return: the list of registered worker hostnames
        :rtype: list[str]
        """
        raw_network_response = network.get(worker_api_url)
        response_data = raw_network_response.json()

        if 'workers' not in response_data:
            raise RuntimeError('Received invalid response from API call to {} with contents: {}'.format(
                worker_api_url, raw_network_response))

        registered_worker_hosts = []

        for worker_response in response_data['workers']:
            worker_url = worker_response['url']

            # In order to urlparse's 'hostname' attribute to get properly set, the url must start with the scheme
            if not worker_url.startswith('http'):
                worker_url = '{}://{}'.format(Configuration['protocol_scheme'], worker_url)

            # Must strip out the port and scheme
            registered_worker_hosts.append(urlparse(worker_url).hostname)

        return registered_worker_hosts

    def _non_registered_workers(self, registered_workers, workers_to_validate):
        """
        Return list of worker hosts that have failed to register with the manager service.

        :param workers_to_validate: list of worker hostnames to check for
        :type workers_to_validate: list[str]
        :return: list of worker hostnames that haven't registered with the manager service yet
        :rtype: list[str]
        """
        registered_host_ids = [Network.get_host_id(worker) for worker in registered_workers]

        workers_to_validate_host_id_pairs = {
            Network.get_host_id(worker): worker
            for worker in workers_to_validate
        }

        non_registered_worker_hosts = [
            workers_to_validate_host_id_pairs[host_id] for host_id in workers_to_validate_host_id_pairs
            if host_id not in registered_host_ids
        ]

        return non_registered_worker_hosts

    def _get_loaded_config(self, conf_file_path, conf_loader):
        """
        :param conf_file_path: path to the configuration file
        :type conf_file_path: str
        :type conf_loader: BaseConfigLoader
        :rtype: Configuration
        """
        config = Configuration(as_instance=True)
        conf_loader.configure_defaults(config)
        conf_loader.load_from_config_file(config, conf_file_path)
        conf_loader.configure_postload(config)
        return config
