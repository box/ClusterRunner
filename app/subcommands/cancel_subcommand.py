from app.client.cluster_api_client import ClusterMasterAPIClient
from app.subcommands.subcommand import Subcommand
from app.util import log
from app.util.conf.configuration import Configuration


class CancelSubcommand(Subcommand):

    def run(self, log_level, master_url, build_id, **request_params):
        """
        Execute a build and wait for it to complete.

        :param log_level: the log level at which to do application logging (or None for default log level)
        :type log_level: str | None
        :param master_url: the url (specified by the user) of the master to which we should send the build
        :type master_url: str | None
        :param build_id: The build to cancel
        :type build_id: int
        :param request_params: key-value pairs to be provided as build parameters in the build request
        :type request_params: dict
        """
        log_level = log_level or Configuration['log_level']
        log.configure_logging(log_level=log_level, simplified_console_logs=True)

        master_url = master_url or '{}:{}'.format(Configuration['hostname'], Configuration['port'])
        client = ClusterMasterAPIClient(master_url)
        client.cancel_build(build_id)

