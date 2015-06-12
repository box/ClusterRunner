from app.client.cluster_api_client import ClusterMasterAPIClient
from app.subcommands.subcommand import Subcommand
from app.util import log
from app.util.conf.configuration import Configuration


class ShutdownSubcommand(Subcommand):

    def run(self, log_level, master_url, slave_ids=None, all_slaves=False, **request_params):
        log_level = log_level or Configuration['log_level']
        log.configure_logging(log_level=log_level, simplified_console_logs=True)

        master_url = master_url or '{}:{}'.format(Configuration['hostname'], Configuration['port'])
        client = ClusterMasterAPIClient(master_url)
        if all_slaves:
            client.graceful_shutdown_all_slaves()
        elif slave_ids and len(slave_ids) > 0:
            client.graceful_shutdown_slaves_by_id(slave_ids)
        else:
            self._logger.error('No slaves specified to shutdown.')
            exit(1)
