import getpass
from multiprocessing.dummy import Pool
import os
from os.path import join
import sys
from urllib.parse import urlparse

import requests

from app.client.build_runner import BuildRunner
from app.deployment.deploy_target import DeployTarget
from app.deployment.remote_master_service import RemoteMasterService
from app.deployment.remote_slave_service import RemoteSlaveService
from app.subcommands.subcommand import Subcommand
from app.util.poll import wait_for
from app.util import fs, log
from app.util.conf.configuration import Configuration
from app.util.conf.master_config_loader import MasterConfigLoader
from app.util.conf.slave_config_loader import SlaveConfigLoader
from app.util.network import Network
from app.util.url_builder import UrlBuilder


class DeploySubcommand(Subcommand):
    _logger = log.get_logger(__name__)
    # Number of seconds to wait for all of the slave services to successfully register with the master service
    _SLAVE_REGISTRY_TIMEOUT_SEC = 5

    def run(self, log_level, master, master_port, slaves, slave_port, num_executors):
        """
        'Deploy' can be a vague word, so we should be specific about what this command accomplishes.

        This command will:
        - Replace the existing binary files in the slaves and master hosts with the binary files running this
          command currently. If there is nothing to replace, this command will just place the binary files there.
        - Stop all clusterrunner services running on all slaves and the master.
        - Start the master and slave services on the master and slave hosts.
        - Poll until timeout to validate that the master service has started, and that the slaves have successfully
          connected with the master.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param master: the master hostname (no port) to deploy the master service to
        :type master: str | None
        :param master_port: the port number the master service will listen on
        :type master_port: int | None
        :param slaves: list of slave hostnames (no ports) to deploy the slave service to
        :type slaves: [str] | None
        :param slave_port: the port number the slave services will listen on
        :type slave_port: int | None
        :param num_executors: the number of executors that will be run per slave
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
        slave_config = self._get_loaded_config(conf_path, SlaveConfigLoader())
        master_config = self._get_loaded_config(conf_path, MasterConfigLoader())
        master = master or slave_config.get('master_hostname')
        master_port = master_port or master_config.get('port')
        slaves = slaves or master_config.get('slaves')
        slave_port = slave_port or slave_config.get('port')
        num_executors = num_executors or slave_config.get('num_executors')
        clusterrunner_executable_dir = join(os.path.expanduser('~'), '.clusterrunner', 'dist')
        clusterrunner_executable = join(clusterrunner_executable_dir, 'clusterrunner')

        self._logger.info('Compressing binaries...')
        binaries_tar_path = self._binaries_tar(current_executable, Configuration['root_directory'])

        self._logger.info('Deploying binaries and confs on master and slaves...')
        arguments = [[host, username, current_executable, binaries_tar_path, conf_path] for host in slaves + [master]]
        Pool().starmap(self._deploy_binaries_and_conf, arguments)

        self._logger.info('Stopping and starting all clusterrunner services...')
        self._start_services(master, master_port, slaves, slave_port, num_executors, username, clusterrunner_executable)

        self._logger.info('Validating successful deployment...')
        master_service_url = '{}:{}'.format(master, master_port)
        self._validate_successful_deployment(master_service_url, slaves)

        self._logger.info('Deploy SUCCESS to slaves: {}'.format(','.join(slaves)))

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

        fs.compress_directory(clusterrunner_bin_dir, tar_file_path)
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

    def _start_services(self, master, master_port, slaves, slave_port, num_executors, username, clusterrunner_executable):
        """
        Stop and start the appropriate clusterrunner services on all machines.

        :param master: master hostnames
        :type master: str
        :param master_port: master's port
        :type master_port: int
        :param slaves: slave hostnames
        :type slaves: list[str]
        :param slave_port: slave's port
        :type slave_port: int
        :param num_executors: number of concurrent executors
        :type num_executors: int
        :param username: current username
        :type username: str
        :param clusterrunner_executable: where the clusterrunner executable on the remote hosts is expected to be
        :type clusterrunner_executable: str
        """
        # We want to stop slave services before the master service, as that is a more graceful shutdown and also
        # reduces the risk of a race condition where the slave service sends a slave-shutdown request to the master
        # after the new master service starts.
        self._logger.debug('Stopping all slave services')
        slave_services = [RemoteSlaveService(slave, username, clusterrunner_executable) for slave in slaves]
        Pool().map(lambda slave_service: slave_service.stop(), slave_services)

        self._logger.debug('Stopping master service on {}...'.format(master))
        master_service = RemoteMasterService(master, username, clusterrunner_executable)
        master_service.stop()

        self._logger.debug('Starting master service on {}:{}'.format(master_service.host, master_port))
        master_service.start_and_block_until_up(master_port)

        self._logger.debug('Starting slave services')

        for slave_service in slave_services:
            try:
                slave_service.start(master, master_port, slave_port, num_executors)
            except Exception as e:  # pylint: disable=broad-except
                self._logger.error('Failed to start slave service on {} with message: {}'.format(slave_service.host, e))

    def _validate_successful_deployment(self, master_service_url, slaves_to_validate):
        """
        Poll the master's /slaves endpoint until either timeout or until all of the slaves have registered with
        the master.

        Throws exception upon timeout or API response error.

        :param master_service_url: the hostname:port for the running master service
        :type master_service_url: str
        :param slaves_to_validate: the list of slave hostnames (no ports) to deploy to
        :type slaves_to_validate: list[str]
        """
        master_api = UrlBuilder(master_service_url, BuildRunner.API_VERSION)
        slave_api_url = master_api.url('slave')
        network = Network()

        def all_slaves_registered():
            registered_slave_uids = set(
                [Network.get_host_id(x) for x in self._registered_slave_hostnames(slave_api_url, network)]
            )
            slaves_to_validate_uids = set(
                [Network.get_host_id(x) for x in slaves_to_validate]
            )
            return registered_slave_uids == slaves_to_validate_uids

        if not wait_for(
                boolean_predicate=all_slaves_registered,
                timeout_seconds=self._SLAVE_REGISTRY_TIMEOUT_SEC,
                poll_period=1,
                exceptions_to_swallow=(requests.RequestException, requests.ConnectionError)
        ):
            try:
                registered_slaves = self._registered_slave_hostnames(slave_api_url, network)
                non_registered_slaves = self._non_registered_slaves(registered_slaves, slaves_to_validate)
            except ConnectionError:
                self._logger.error('Error contacting {} on the master.'.format(slave_api_url))
                raise SystemExit(1)

            self._logger.error('Slave registration timed out after {} sec, with slaves {} missing.'.format(
                self._SLAVE_REGISTRY_TIMEOUT_SEC, ','.join(non_registered_slaves)))
            raise SystemExit(1)

    def _registered_slave_hostnames(self, slave_api_url, network):
        """
        Return list of slave hosts that have registered with the master service.

        :param slave_api_url: url to the master's '/slave' endpoint
        :type slave_api_url: str
        :param network: the Network instance (so that we don't have to reinstantiate it many times)
        :type network: Network
        :return: the list of registered slave hostnames
        :rtype: list[str]
        """
        raw_network_response = network.get(slave_api_url)
        response_data = raw_network_response.json()

        if 'slaves' not in response_data:
            raise RuntimeError('Received invalid response from API call to {} with contents: {}'.format(
                slave_api_url, raw_network_response))

        registered_slave_hosts = []

        for slave_response in response_data['slaves']:
            slave_url = slave_response['url']

            # In order to urlparse's 'hostname' attribute to get properly set, the url must start with the scheme
            if not slave_url.startswith('http'):
                slave_url = 'http://{}'.format(slave_url)

            # Must strip out the port and scheme
            registered_slave_hosts.append(urlparse(slave_url).hostname)

        return registered_slave_hosts

    def _non_registered_slaves(self, registered_slaves, slaves_to_validate):
        """
        Return list of slave hosts that have failed to register with the master service.

        :param slaves_to_validate: list of slave hostnames to check for
        :type slaves_to_validate: list[str]
        :return: list of slave hostnames that haven't registered with the master service yet
        :rtype: list[str]
        """
        registered_host_ids = [Network.get_host_id(slave) for slave in registered_slaves]

        slaves_to_validate_host_id_pairs = {
            Network.get_host_id(slave): slave
            for slave in slaves_to_validate
        }

        non_registered_slave_hosts = [
            slaves_to_validate_host_id_pairs[host_id] for host_id in slaves_to_validate_host_id_pairs
            if host_id not in registered_host_ids
        ]

        return non_registered_slave_hosts

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
