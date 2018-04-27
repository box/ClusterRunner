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

    def run(self, log_level, manager_url, remote_file=None, build_type=None, **request_params):
        """
        Execute a build and wait for it to complete.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param manager_url: the url (specified by the user) of the manager to which we should send the build
        :type manager_url: str | None
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

        operational_manager_url = manager_url or '{}:{}'.format(Configuration['hostname'], Configuration['port'])

        # If running a single manager, single worker--both on localhost--we need to launch services locally.
        if manager_url is None and Network.are_hosts_same(Configuration['manager_hostname'], 'localhost') \
                and len(Configuration['workers']) == 1 \
                and Network.are_hosts_same(Configuration['workers'][0], 'localhost'):
            self._start_local_services_if_needed(operational_manager_url)

        if request_params['type'] == 'directory':
            request_params['project_directory'] = request_params.get('project_directory') or os.getcwd()

        runner = BuildRunner(manager_url=operational_manager_url, request_params=request_params, secret=Secret.get())

        if not runner.run():
            sys.exit(1)

    def _start_local_services_if_needed(self, manager_url):
        """
        In the case that:

        - the manager url is localhost
        - the workers list is just localhost

        Start a manager and worker service instance locally, if the manager is not already running.

        :param manager_url: service url (with port number)
        :type manager_url: str
        """
        service_runner = ServiceRunner(manager_url)
        if service_runner.is_manager_up():
            return
        try:
            service_runner.run_manager()
            service_runner.run_worker()
        except ServiceRunError as ex:
            self._logger.error(str(ex))
            sys.exit(1)
