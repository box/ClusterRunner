from app.client.cluster_api_client import ClusterManagerAPIClient
from app.subcommands.subcommand import Subcommand
from app.util import log
from app.util.conf.configuration import Configuration


class ShutdownSubcommand(Subcommand):

    def run(self, log_level, manager_url, worker_ids=None, all_workers=False, **request_params):
        log_level = log_level or Configuration['log_level']
        log.configure_logging(log_level=log_level, simplified_console_logs=True)

        manager_url = manager_url or '{}:{}'.format(Configuration['hostname'], Configuration['port'])
        client = ClusterManagerAPIClient(manager_url)
        if all_workers:
            client.graceful_shutdown_all_workers()
        elif worker_ids and len(worker_ids) > 0:
            client.graceful_shutdown_workers_by_id(worker_ids)
        else:
            self._logger.error('No workers specified to shutdown.')
            exit(1)
