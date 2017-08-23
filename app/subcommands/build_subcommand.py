import os
import sys

from app.client.build_runner import BuildRunner
from app.client.service_runner import ServiceRunner, ServiceRunError
from app.subcommands.subcommand import Subcommand
from app.util import log
from app.util.conf.configuration import Configuration
from app.util.network import Network
from app.util.secret import Secret


class BuildSubcommand(Subcommand):

    def run(self, log_level, master_url, remote_file=None, build_type=None, **request_params):
        """
        Execute a build and wait for it to complete.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param master_url: the url (specified by the user) of the master to which we should send the build
        :type master_url: str | None
        :param remote_file: a list of remote files where each element contains the output file name and the resource URL
        :type remote_file: list[list[str]] | None
        :param build_type: the build type of the request to be sent (e.g., "git", "directory"). If not specified
            will default to the "directory" project type.
        :type build_type: str | None
        :param request_params: key-value pairs to be provided as build parameters in the build request
        :type request_params: dict
        """
        log_level = log_level or Configuration['log_level']
        log.configure_logging(log_level=log_level, simplified_console_logs=True)
        request_params['type'] = build_type or request_params.get('type') or 'directory'

        if remote_file:
            request_params['remote_files'] = {name: url for name, url in remote_file}

        operational_master_url = master_url or '{}:{}'.format(Configuration['hostname'], Configuration['port'])

        # If running a single master, single slave--both on localhost--we need to launch services locally.
        if master_url is None and Network.are_hosts_same(Configuration['master_hostname'], 'localhost') \
                and len(Configuration['slaves']) == 1 \
                and Network.are_hosts_same(Configuration['slaves'][0], 'localhost'):
            self._start_local_services_if_needed(operational_master_url)

        if request_params['type'] == 'directory':
            request_params['project_directory'] = request_params.get('project_directory') or os.getcwd()

        runner = BuildRunner(master_url=operational_master_url, request_params=request_params, secret=Secret.get())

        if not runner.run():
            sys.exit(1)

    def _start_local_services_if_needed(self, master_url):
        """
        In the case that:

        - the master url is localhost
        - the slaves list is just localhost

        Start a master and slave service instance locally, if the master is not already running.

        :param master_url: service url (with port number)
        :type master_url: str
        """
        service_runner = ServiceRunner(master_url)
        if service_runner.is_master_up():
            return
        try:
            service_runner.run_master()
            service_runner.run_slave()
        except ServiceRunError as ex:
            self._logger.error(str(ex))
            sys.exit(1)
