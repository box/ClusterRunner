import http.client
import os
import urllib.parse

import tornado.web

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

class ClusterMasterApplication(ClusterApplication):

    def __init__(self, cluster_master):
        """
        :type cluster_master: ClusterMaster
        """
        default_params = {
            'cluster_master': cluster_master,
        }
        # The routes are described using a tree structure.  This is a better representation of a path than a flat list
        #  of strings and allows us to inspect children/parents of a node to generate 'child routes'
        root_route = \
            RouteNode(r'/', _RootHandler).add_children([
                RouteNode(r'v1', _APIVersionOneHandler).add_children([
                    RouteNode(r'version', _VersionHandler),
                    RouteNode(r'build', _BuildsHandler, 'builds').add_children([
                        RouteNode(r'(\d+)', _BuildHandler, 'build').add_children([
                            RouteNode(r'result', _BuildResultRedirectHandler),
                            RouteNode(r'artifacts.tar.gz', _BuildResultHandler),
                            RouteNode(r'subjob', _SubjobsHandler, 'subjobs').add_children([
                                RouteNode(r'(\d+)', _SubjobHandler, 'subjob').add_children([
                                    RouteNode(r'atom', _AtomsHandler, 'atoms').add_children([
                                        RouteNode(r'(\d+)', _AtomHandler, 'atom').add_children([
                                            RouteNode(r'console', _AtomConsoleHandler)
                                        ])
                                    ]),
                                    RouteNode(r'result', _SubjobResultHandler)
                                ])
                            ])
                        ])
                    ]),
                    RouteNode(r'queue', _QueueHandler),
                    RouteNode(r'slave', _SlavesHandler, 'slaves').add_children([
                        RouteNode(r'(\d+)', _SlaveHandler, 'slave').add_children([
                            RouteNode(r'shutdown', _SlaveShutdownHandler, 'shutdown')
                        ]),
                        RouteNode(r'shutdown', _SlavesShutdownHandler, 'shutdown')
                    ]),
                    RouteNode(r'eventlog', _EventlogHandler)
                ])
            ])
        handlers = self.get_all_handlers(root_route, default_params)
        super().__init__(handlers)


class _ClusterMasterBaseAPIHandler(ClusterBaseAPIHandler):
    def initialize(self, route_node=None, cluster_master=None):
        """
        :type route_node: RouteNode | None
        :type cluster_master: ClusterMaster | None
        """
        self._logger = log.get_logger(__name__)
        self._cluster_master = cluster_master
        super().initialize(route_node)


class _RootHandler(_ClusterMasterBaseAPIHandler):
    pass


class _APIVersionOneHandler(_ClusterMasterBaseAPIHandler):
    def get(self):
        response = {
            'master': self._cluster_master.api_representation(),
        }
        self.write(response)


class _VersionHandler(_ClusterMasterBaseAPIHandler):
    def get(self):
        response = {
            'version': Configuration['version'],
        }
        self.write(response)


class _QueueHandler(_ClusterMasterBaseAPIHandler):
    def get(self):
        response = {
            'queue': [build.api_representation() for build in self._cluster_master.active_builds()]
        }
        self.write(response)


class _SubjobsHandler(_ClusterMasterBaseAPIHandler):
    def get(self, build_id):
        build = self._cluster_master.get_build(int(build_id))
        response = {
            'subjobs': [subjob.api_representation() for subjob in build.all_subjobs()]
        }
        self.write(response)


class _SubjobHandler(_ClusterMasterBaseAPIHandler):
    def get(self, build_id, subjob_id):
        build = self._cluster_master.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'subjob': subjob.api_representation()
        }
        self.write(response)


class _SubjobResultHandler(_ClusterMasterBaseAPIHandler):
    def post(self, build_id, subjob_id):
        slave_url = self.decoded_body.get('slave')
        slave = self._cluster_master.get_slave(slave_url=slave_url)
        file_payload = self.request.files.get('file')
        if not file_payload:
            raise RuntimeError('Result file not provided')

        slave_executor_id = self.decoded_body.get('metric_data', {}).get('executor_id')
        analytics.record_event(analytics.MASTER_RECEIVED_RESULT, executor_id=slave_executor_id, build_id=int(build_id),
                               subjob_id=int(subjob_id), slave_id=slave.id)

        self._cluster_master.handle_result_reported_from_slave(
            slave_url, int(build_id), int(subjob_id), file_payload[0])
        self._write_status()

    def get(self, build_id, subjob_id):
        # TODO: return the subjob's result archive here?
        self.write({'status': 'not implemented'})


class _AtomsHandler(_ClusterMasterBaseAPIHandler):
    def get(self, build_id, subjob_id):
        build = self._cluster_master.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'atoms': [atom.api_representation() for atom in subjob.atoms()],
        }
        self.write(response)


class _AtomHandler(_ClusterMasterBaseAPIHandler):
    def get(self, build_id, subjob_id, atom_id):
        build = self._cluster_master.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        atoms = subjob.atoms
        response = {
            'atom': atoms[int(atom_id)].api_representation(),
        }
        self.write(response)


class _AtomConsoleHandler(_ClusterMasterBaseAPIHandler):
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
            response = self._cluster_master.get_console_output(
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
            # If the master doesn't have the atom's console output, it's possible it's currently being worked on,
            # in which case the slave that is working on it may be able to provide the in-progress console output.
            build = self._cluster_master.get_build(int(build_id))
            subjob = build.subjob(int(subjob_id))
            slave = subjob.slave

            if slave is None:
                raise e

            api_url_builder = UrlBuilder(slave.url)
            slave_console_url = api_url_builder.url('build', build_id, 'subjob', subjob_id, 'atom', atom_id, 'console')
            query = {'max_lines': max_lines}

            if offset_line is not None:
                query['offset_line'] = offset_line

            query_string = urllib.parse.urlencode(query)
            self.redirect('{}?{}'.format(slave_console_url, query_string))


class _BuildsHandler(_ClusterMasterBaseAPIHandler):
    @authenticated
    def post(self):
        build_params = self.decoded_body
        success, response = self._cluster_master.handle_request_for_new_build(build_params)
        status_code = http.client.ACCEPTED if success else http.client.BAD_REQUEST
        self._write_status(response, success, status_code=status_code)

    def get(self):
        response = {
            'builds': [build.api_representation() for build in self._cluster_master.builds()]
        }
        self.write(response)


class _BuildHandler(_ClusterMasterBaseAPIHandler):
    @authenticated
    def put(self, build_id):
        update_params = self.decoded_body
        success, response = self._cluster_master.handle_request_to_update_build(build_id, update_params)
        status_code = http.client.OK if success else http.client.BAD_REQUEST
        self._write_status(response, success, status_code=status_code)

    def get(self, build_id):
        response = {
            'build': self._cluster_master.get_build(int(build_id)).api_representation(),
        }
        self.write(response)


class _BuildResultRedirectHandler(_ClusterMasterBaseAPIHandler):
    """
    Redirect to the actual build results file download URL.
    """
    def get(self, build_id):
        self.redirect('/v1/build/{}/artifacts.tar.gz'.format(build_id))


class _BuildResultHandler(ClusterBaseHandler, tornado.web.StaticFileHandler):
    """
    Download an artifact for the specified build. Note this class inherits from ClusterBaseHandler and
    StaticFileHandler, so the semantics of this handler are a bit different than the other handlers in this file that
    inherit from _ClusterMasterBaseHandler.

    From the Tornado docs: "for heavy traffic it will be more efficient to use a dedicated static file server".
    """
    def initialize(self, route_node=None, cluster_master=None):
        """
        :param route_node: This is not used, it is only a param so we can pass route_node to all handlers without error.
        In other routes, route_node is used to find child routes but filehandler routes will never show child routes.
        :type route_node: RouteNode | None
        :type cluster_master: ClusterMaster | None
        """
        self._cluster_master = cluster_master
        super().initialize(path=None)  # we will not set the root path until the get() method is called

    def get(self, build_id, path=None):
        artifact_file_path = self._cluster_master.get_path_for_build_results_archive(int(build_id))
        self.root, artifact_filename = os.path.split(artifact_file_path)
        self.set_header('Content-Type', 'application/octet-stream')  # this should be downloaded as a binary file
        return super().get(path=artifact_filename)


class _SlavesHandler(_ClusterMasterBaseAPIHandler):
    def post(self):
        slave_url = self.decoded_body.get('slave')
        num_executors = int(self.decoded_body.get('num_executors'))
        session_id = self.decoded_body.get('session_id')
        response = self._cluster_master.connect_slave(slave_url, num_executors, session_id)
        self._write_status(response, status_code=201)

    def get(self):
        response = {
            'slaves': [slave.api_representation() for slave in self._cluster_master.all_slaves_by_id().values()]
        }
        self.write(response)


class _SlaveHandler(_ClusterMasterBaseAPIHandler):
    def get(self, slave_id):
        slave = self._cluster_master.get_slave(int(slave_id))
        response = {
            'slave': slave.api_representation()
        }
        self.write(response)

    @authenticated
    def put(self, slave_id):
        new_slave_state = self.decoded_body.get('slave', {}).get('state')
        slave = self._cluster_master.get_slave(int(slave_id))
        self._cluster_master.handle_slave_state_update(slave, new_slave_state)

        self._write_status({
            'slave': slave.api_representation()
        })


class _EventlogHandler(_ClusterMasterBaseAPIHandler):
    def get(self):
        # all arguments are optional, so default to None
        since_timestamp = self.get_query_argument('since_timestamp', None)
        since_id = self.get_query_argument('since_id', None)
        self.write({
            'events': analytics.get_events(since_timestamp, since_id),
        })


class _SlaveShutdownHandler(_ClusterMasterBaseAPIHandler):
    @authenticated
    def post(self, slave_id):
        slaves_to_shutdown = [int(slave_id)]

        self._cluster_master.set_shutdown_mode_on_slaves(slaves_to_shutdown)


class _SlavesShutdownHandler(_ClusterMasterBaseAPIHandler):
    @authenticated
    def post(self):
        shutdown_all = self.decoded_body.get('shutdown_all')
        slaves_to_shutdown = self._cluster_master.all_slaves_by_id().keys() if shutdown_all else\
            [int(slave_id) for slave_id in self.decoded_body.get('slaves')]

        self._cluster_master.set_shutdown_mode_on_slaves(slaves_to_shutdown)
