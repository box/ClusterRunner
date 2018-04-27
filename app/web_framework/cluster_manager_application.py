import http.client
import os
import urllib.parse

import tornado.web
import prometheus_client

from app.manager.worker import WorkerRegistry
from app.util import analytics
from app.util import log
from app.util.conf.configuration import Configuration
from app.util.decorators import authenticated
from app.util.exceptions import ItemNotFoundError
from app.util.url_builder import UrlBuilder
from app.web_framework.cluster_application import ClusterApplication
from app.web_framework.cluster_base_handler import ClusterBaseAPIHandler, ClusterBaseHandler
from app.web_framework.route_node import RouteNode


# pylint: disable=attribute-defined-outside-init
#   Handler classes are not designed to have __init__ overridden.

class ClusterManagerApplication(ClusterApplication):

    def __init__(self, cluster_manager):
        """
        :type cluster_manager: app.manager.cluster_manager.ClusterManager
        """
        default_params = {
            'cluster_manager': cluster_manager,
        }
        # The routes are described using a tree structure.  This is a better representation of a path than a flat list
        #  of strings and allows us to inspect children/parents of a node to generate 'child routes'
        api_v1 = [
            RouteNode(r'v1', _APIVersionOneHandler).add_children([
                RouteNode(r'metrics', _MetricsHandler),
                RouteNode(r'version', _VersionHandler),
                RouteNode(r'build', _BuildsHandler, 'builds').add_children([
                    RouteNode(r'(\d+)', _BuildHandler, 'build').add_children([
                        RouteNode(r'result', _BuildResultRedirectHandler),
                        RouteNode(r'artifacts.tar.gz', _BuildTarResultHandler),
                        RouteNode(r'artifacts.zip', _BuildZipResultHandler),
                        RouteNode(r'subjob', _SubjobsHandler, 'subjobs').add_children([
                            RouteNode(r'(\d+)', _SubjobHandler, 'subjob').add_children([
                                RouteNode(r'atom', _AtomsHandler, 'atoms').add_children([
                                    RouteNode(r'(\d+)', _AtomHandler, 'atom').add_children([
                                        RouteNode(r'console', _AtomConsoleHandler),
                                    ]),
                                ]),
                                RouteNode(r'result', _SubjobResultHandler),
                            ]),
                        ]),
                    ]),
                ]),
                RouteNode(r'queue', _QueueHandler),
                RouteNode(r'worker', _WorkersHandler, 'workers').add_children([
                    RouteNode(r'(\d+)', _WorkerHandler, 'worker').add_children([
                        RouteNode(r'shutdown', _WorkerShutdownHandler, 'shutdown'),
                        RouteNode(r'heartbeat', _WorkersHeartbeatHandler),
                    ]),
                    RouteNode(r'shutdown', _WorkersShutdownHandler, 'shutdown'),
                ]),
                RouteNode(r'eventlog', _EventlogHandler)])]

        api_v2 = [
            RouteNode(r'metrics', _MetricsHandler),
            RouteNode(r'version', _VersionHandler),
            RouteNode(r'builds', _V2BuildsHandler).add_children([
                RouteNode(r'(\d+)', _BuildHandler, 'build').add_children([
                    RouteNode(r'result', _BuildResultRedirectHandler),
                    RouteNode(r'artifacts.tar.gz', _BuildTarResultHandler),
                    RouteNode(r'artifacts.zip', _BuildZipResultHandler),
                    RouteNode(r'subjobs', _V2SubjobsHandler,).add_children([
                        RouteNode(r'(\d+)', _SubjobHandler, 'subjob').add_children([
                            RouteNode(r'atoms', _V2AtomsHandler).add_children([
                                RouteNode(r'(\d+)', _AtomHandler, 'atom').add_children([
                                    RouteNode(r'console', _AtomConsoleHandler),
                                ]),
                            ]),
                            RouteNode(r'result', _SubjobResultHandler),
                        ]),
                    ]),
                ]),
            ]),
            RouteNode(r'queue', _QueueHandler),
            RouteNode(r'workers', _WorkersHandler).add_children([
                RouteNode(r'(\d+)', _WorkerHandler, 'worker').add_children([
                    RouteNode(r'shutdown', _WorkerShutdownHandler),
                    RouteNode(r'heartbeat', _WorkersHeartbeatHandler),
                ]),
                RouteNode(r'shutdown', _WorkersShutdownHandler),
            ]),
            RouteNode(r'eventlog', _EventlogHandler)]

        root = RouteNode(r'/', _RootHandler)
        root.add_children(api_v1, version=1)
        root.add_children(api_v2, version=2)

        handlers = self.get_all_handlers(root, default_params)
        super().__init__(handlers)


class _ClusterManagerBaseAPIHandler(ClusterBaseAPIHandler):
    def initialize(self, route_node=None, cluster_manager=None):
        """
        :type route_node: RouteNode
        :type cluster_manager: app.manager.cluster_manager.ClusterManager
        """
        self._logger = log.get_logger(__name__)
        self._cluster_manager = cluster_manager
        super().initialize(route_node)


class _RootHandler(_ClusterManagerBaseAPIHandler):
    pass


class _APIVersionOneHandler(_ClusterManagerBaseAPIHandler):
    def get(self):
        response = {
            'manager': self._cluster_manager.api_representation(),
        }
        self.write(response)


class _VersionHandler(_ClusterManagerBaseAPIHandler):
    def get(self):
        response = {
            'version': Configuration['version'],
            'api_version': self.api_version,
        }
        self.write(response)


class _MetricsHandler(_ClusterManagerBaseAPIHandler):
    def get(self):
        self.write_text(prometheus_client.exposition.generate_latest(prometheus_client.core.REGISTRY))


class _QueueHandler(_ClusterManagerBaseAPIHandler):
    def get(self):
        response = {
            'queue': [build.api_representation() for build in self._cluster_manager.active_builds()]
        }
        self.write(response)


class _SubjobsHandler(_ClusterManagerBaseAPIHandler):
    def get(self, build_id):
        build = self._cluster_manager.get_build(int(build_id))
        response = {
            'subjobs': [subjob.api_representation() for subjob in build.get_subjobs()]
        }
        self.write(response)


class _V2SubjobsHandler(_SubjobsHandler):
    def get(self, build_id):
        offset, limit = self.get_pagination_params()
        build = self._cluster_manager.get_build(int(build_id))
        response = {
            'subjobs': [subjob.api_representation() for subjob in build.get_subjobs(offset, limit)]
        }
        self.write(response)


class _SubjobHandler(_ClusterManagerBaseAPIHandler):
    def get(self, build_id, subjob_id):
        build = self._cluster_manager.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'subjob': subjob.api_representation()
        }
        self.write(response)


class _SubjobResultHandler(_ClusterManagerBaseAPIHandler):
    def post(self, build_id, subjob_id):
        worker_url = self.decoded_body.get('worker')
        worker = WorkerRegistry.singleton().get_worker(worker_url=worker_url)
        file_payload = self.request.files.get('file')
        if not file_payload:
            raise RuntimeError('Result file not provided')

        worker_executor_id = self.decoded_body.get('metric_data', {}).get('executor_id')
        analytics.record_event(analytics.MASTER_RECEIVED_RESULT, executor_id=worker_executor_id, build_id=int(build_id),
                               subjob_id=int(subjob_id), worker_id=worker.id)

        self._cluster_manager.handle_result_reported_from_worker(
            worker_url, int(build_id), int(subjob_id), file_payload[0])
        self._write_status()

    def get(self, build_id, subjob_id):
        # TODO: return the subjob's result archive here?
        self.write({'status': 'not implemented'})


class _AtomsHandler(_ClusterManagerBaseAPIHandler):
    def get(self, build_id, subjob_id):
        build = self._cluster_manager.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'atoms': [atom.api_representation() for atom in subjob.atoms()],
        }
        self.write(response)


class _V2AtomsHandler(_AtomsHandler):
    def get(self, build_id, subjob_id):
        offset, limit = self.get_pagination_params()
        build = self._cluster_manager.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'atoms': [atom.api_representation() for atom in subjob.get_atoms(offset, limit)],
        }
        self.write(response)


class _AtomHandler(_ClusterManagerBaseAPIHandler):
    def get(self, build_id, subjob_id, atom_id):
        build = self._cluster_manager.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        atoms = subjob.atoms
        response = {
            'atom': atoms[int(atom_id)].api_representation(),
        }
        self.write(response)


class _AtomConsoleHandler(_ClusterManagerBaseAPIHandler):
    def get(self, build_id, subjob_id, atom_id):
        """
        :type build_id: int
        :type subjob_id: int
        :type atom_id: int
        """
        max_lines = int(self.get_query_argument('max_lines', 50))
        offset_line = self.get_query_argument('offset_line', None)

        if offset_line is not None:
            offset_line = int(offset_line)

        try:
            response = self._cluster_manager.get_console_output(
                build_id,
                subjob_id,
                atom_id,
                Configuration['results_directory'],
                max_lines,
                offset_line
            )
            self.write(response)
            return
        except ItemNotFoundError as e:
            # If the manager doesn't have the atom's console output, it's possible it's currently being worked on,
            # in which case the worker that is working on it may be able to provide the in-progress console output.
            build = self._cluster_manager.get_build(int(build_id))
            subjob = build.subjob(int(subjob_id))
            worker = subjob.worker

            if worker is None:
                raise e

            api_url_builder = UrlBuilder(worker.url)
            worker_console_url = api_url_builder.url('build', build_id, 'subjob', subjob_id, 'atom', atom_id, 'console')
            query = {'max_lines': max_lines}

            if offset_line is not None:
                query['offset_line'] = offset_line

            query_string = urllib.parse.urlencode(query)
            self.redirect('{}?{}'.format(worker_console_url, query_string))


class _BuildsHandler(_ClusterManagerBaseAPIHandler):
    @authenticated
    def post(self):
        build_params = self.decoded_body
        success, response = self._cluster_manager.handle_request_for_new_build(build_params)
        status_code = http.client.ACCEPTED if success else http.client.BAD_REQUEST
        self._write_status(response, success, status_code=status_code)

    def get(self):
        response = {
            'builds': [build.api_representation() for build in self._cluster_manager.get_builds()]
        }
        self.write(response)


class _V2BuildsHandler(_BuildsHandler):
    def get(self):
        offset, limit = self.get_pagination_params()
        response = {
            'builds': [build.api_representation() for build in self._cluster_manager.get_builds(offset, limit)]
        }
        self.write(response)


class _BuildHandler(_ClusterManagerBaseAPIHandler):
    @authenticated
    def put(self, build_id):
        update_params = self.decoded_body
        success, response = self._cluster_manager.handle_request_to_update_build(build_id, update_params)
        status_code = http.client.OK if success else http.client.BAD_REQUEST
        self._write_status(response, success, status_code=status_code)

    def get(self, build_id):
        response = {
            'build': self._cluster_manager.get_build(int(build_id)).api_representation(),
        }
        self.write(response)


class _BuildResultRedirectHandler(_ClusterManagerBaseAPIHandler):
    """
    Redirect to the actual build results file download URL.
    """
    def get(self, build_id):
        self.redirect('/v1/build/{}/artifacts.tar.gz'.format(build_id))


class _BuildResultHandler(ClusterBaseHandler, tornado.web.StaticFileHandler):
    """
    Download an artifact for the specified build. Note this class inherits from ClusterBaseHandler and
    StaticFileHandler, so the semantics of this handler are a bit different than the other handlers in this file that
    inherit from _ClusterManagerBaseHandler.

    From the Tornado docs: "for heavy traffic it will be more efficient to use a dedicated static file server".
    """
    def initialize(self, route_node=None, cluster_manager=None):
        """
        :param route_node: This is not used, it is only a param so we can pass route_node to all handlers without error.
        In other routes, route_node is used to find child routes but filehandler routes will never show child routes.
        :type route_node: RouteNode | None
        :type cluster_manager: app.manager.cluster_manager.ClusterManager | None
        """
        self._cluster_manager = cluster_manager
        super().initialize(path=None)  # we will not set the root path until the get() method is called

    def get(self, build_id):
        artifact_file_path = self.get_result_file_download_path(int(build_id))
        self.root, artifact_filename = os.path.split(artifact_file_path)
        self.set_header('Content-Type', 'application/octet-stream')  # this should be downloaded as a binary file
        return super().get(path=artifact_filename)

    def get_result_file_download_path(self, build_id: int):
        raise NotImplementedError


class _BuildTarResultHandler(_BuildResultHandler):
    """Handler for the tar archive file"""
    def get_result_file_download_path(self, build_id: int):
        """Get the file path to the artifacts.tar.gz for the specified build."""
        return self._cluster_manager.get_path_for_build_results_archive(build_id, is_tar_request=True)


class _BuildZipResultHandler(_BuildResultHandler):
    """Handler for the zip archive file"""
    def get_result_file_download_path(self, build_id: int):
        """Get the file path to the artifacts.zip for the specified build."""
        return self._cluster_manager.get_path_for_build_results_archive(build_id)


class _WorkersHandler(_ClusterManagerBaseAPIHandler):
    def post(self):
        worker_url = self.decoded_body.get('worker')
        num_executors = int(self.decoded_body.get('num_executors'))
        session_id = self.decoded_body.get('session_id')
        response = self._cluster_manager.connect_worker(worker_url, num_executors, session_id)
        self._write_status(response, status_code=201)

    def get(self):

        response = {
            'workers': [worker.api_representation() for worker in WorkerRegistry.singleton().get_all_workers_by_id().values()]
        }
        self.write(response)


class _WorkerHandler(_ClusterManagerBaseAPIHandler):
    def get(self, worker_id):
        worker = WorkerRegistry.singleton().get_worker(worker_id=int(worker_id))
        response = {
            'worker': worker.api_representation()
        }
        self.write(response)

    @authenticated
    def put(self, worker_id):
        new_worker_state = self.decoded_body.get('worker', {}).get('state')
        worker = WorkerRegistry.singleton().get_worker(worker_id=int(worker_id))
        self._cluster_manager.handle_worker_state_update(worker, new_worker_state)
        self._cluster_manager.update_worker_last_heartbeat_time(worker)

        self._write_status({
            'worker': worker.api_representation()
        })


class _EventlogHandler(_ClusterManagerBaseAPIHandler):
    def get(self):
        # all arguments are optional, so default to None
        since_timestamp = self.get_query_argument('since_timestamp', None)
        since_id = self.get_query_argument('since_id', None)
        self.write({
            'events': analytics.get_events(since_timestamp, since_id),
        })


class _WorkerShutdownHandler(_ClusterManagerBaseAPIHandler):
    @authenticated
    def post(self, worker_id):
        workers_to_shutdown = [int(worker_id)]

        self._cluster_manager.set_shutdown_mode_on_workers(workers_to_shutdown)


class _WorkersShutdownHandler(_ClusterManagerBaseAPIHandler):
    @authenticated
    def post(self):
        shutdown_all = self.decoded_body.get('shutdown_all')
        if shutdown_all:
            workers_to_shutdown = WorkerRegistry.singleton().get_all_workers_by_id().keys()
        else:
            workers_to_shutdown = [int(worker_id) for worker_id in self.decoded_body.get('workers')]

        self._cluster_manager.set_shutdown_mode_on_workers(workers_to_shutdown)


class _WorkersHeartbeatHandler(_ClusterManagerBaseAPIHandler):
    @authenticated
    def post(self, worker_id):
        worker = WorkerRegistry.singleton().get_worker(worker_id=int(worker_id))
        self._cluster_manager.update_worker_last_heartbeat_time(worker)
