import http.client
import os
import tornado.web

from app.util import analytics
from app.util.conf.configuration import Configuration
from app.util.decorators import authenticated
from app.web_framework.cluster_application import ClusterApplication
from app.web_framework.cluster_base_handler import ClusterBaseHandler
from app.web_framework.route_node import RouteNode


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
                                        RouteNode(r'(\d+)', _AtomHandler, 'atom')
                                    ]),
                                    RouteNode(r'result', _SubjobResultHandler)
                                ])
                            ])
                        ])
                    ]),
                    RouteNode(r'queue', _QueueHandler),
                    RouteNode(r'slave', _SlavesHandler, 'slaves').add_children([
                        RouteNode(r'(\d+)', _SlaveHandler, 'slave').add_children([
                            RouteNode(r'idle', _SlaveIdleHandler),
                            RouteNode(r'disconnect', _SlaveDisconnectHandler)
                        ])
                    ]),
                    RouteNode(r'eventlog', _EventlogHandler)
                ])
            ])
        handlers = self.get_all_handlers(root_route, default_params)
        super().__init__(handlers)


class _ClusterMasterBaseHandler(ClusterBaseHandler):
    def initialize(self, route_node=None, cluster_master=None):
        """
        :type route_node: RouteNode | None
        :type cluster_master: ClusterMaster | None
        """
        self._cluster_master = cluster_master
        super().initialize(route_node)


class _RootHandler(_ClusterMasterBaseHandler):
    pass


class _APIVersionOneHandler(_ClusterMasterBaseHandler):
    pass


class _VersionHandler(_ClusterMasterBaseHandler):
    def get(self):
        response = {
            'version': Configuration['version'],
        }
        self.write(response)


class _QueueHandler(_ClusterMasterBaseHandler):
    def get(self):
        response = {
            'queue': [build.api_representation() for build in self._cluster_master.active_builds()]
        }
        self.write(response)


class _SubjobsHandler(_ClusterMasterBaseHandler):
    def get(self, build_id):
        build = self._cluster_master.get_build(int(build_id))
        response = {
            'subjobs': [subjob.api_representation() for subjob in build.all_subjobs()]
        }
        self.write(response)


class _SubjobHandler(_ClusterMasterBaseHandler):
    def get(self, build_id, subjob_id):
        build = self._cluster_master.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'subjob': subjob.api_representation()
        }
        self.write(response)


class _SubjobResultHandler(_ClusterMasterBaseHandler):
    def post(self, build_id, subjob_id):
        slave_url = self.decoded_body.get('slave')
        file_payload = self.request.files.get('file')
        if not file_payload:
            raise RuntimeError('Result file not provided')

        metric_data = self.decoded_body.get('metric_data') or {}
        slave_executor_id = metric_data.get('executor_id')
        analytics.record_event(analytics.MASTER_RECEIVED_RESULT, executor_id=slave_executor_id, build_id=int(build_id),
                               subjob_id=int(subjob_id), slave_url=slave_url)

        self._cluster_master.handle_result_reported_from_slave(
            slave_url, int(build_id), int(subjob_id), file_payload[0])
        self._write_status()

    def get(self, build_id, subjob_id):
        # TODO: return the subjob's result archive here?
        self.write({'status': 'not implemented'})


class _AtomsHandler(_ClusterMasterBaseHandler):
    def get(self, build_id, subjob_id):
        build = self._cluster_master.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        response = {
            'atoms': subjob.get_atoms(),
        }
        self.write(response)


class _AtomHandler(_ClusterMasterBaseHandler):
    def get(self, build_id, subjob_id, atom_id):
        build = self._cluster_master.get_build(int(build_id))
        subjob = build.subjob(int(subjob_id))
        atoms = subjob.get_atoms()
        response = {
            'atom': atoms[int(atom_id)],
        }
        self.write(response)


class _BuildsHandler(_ClusterMasterBaseHandler):
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


class _BuildHandler(_ClusterMasterBaseHandler):
    def get(self, build_id):
        response = {
            'build': self._cluster_master.get_build(int(build_id)).api_representation(),
        }
        self.write(response)


class _BuildResultRedirectHandler(_ClusterMasterBaseHandler):
    """
    Redirect to the actual build results file download URL.
    """
    def get(self, build_id):
        self.redirect('/v1/build/{}/artifacts.tar.gz'.format(build_id))


class _BuildResultHandler(tornado.web.StaticFileHandler):
    """
    Download an artifact for the specified build. Note this class inherits from StaticFileHandler, so the semantics
    of this handler are a bit different than the other handlers in this file that inherit from
    _ClusterMasterBaseHandler.

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


class _SlavesHandler(_ClusterMasterBaseHandler):
    def post(self):
        slave_url = self.decoded_body.get('slave')
        num_executors = int(self.decoded_body.get('num_executors'))
        response = self._cluster_master.connect_new_slave(slave_url, num_executors)
        self._write_status(response, status_code=201)

    def get(self):
        response = {
            'slaves': [slave.api_representation() for slave in self._cluster_master.all_slaves_by_id().values()]
        }
        self.write(response)


class _SlaveHandler(_ClusterMasterBaseHandler):
    def get(self, slave_id):
        slave = self._cluster_master.slave(int(slave_id))
        response = {
            'slave': slave.api_representation()
        }
        self.write(response)


class _SlaveIdleHandler(_ClusterMasterBaseHandler):
    def post(self, slave_id):
        slave = self._cluster_master.slave(int(slave_id))
        self._cluster_master.add_idle_slave(slave)
        self._write_status()


class _SlaveDisconnectHandler(_ClusterMasterBaseHandler):
    def post(self, slave_id):
        self._cluster_master.disconnect_slave(int(slave_id))
        self._write_status()


class _EventlogHandler(_ClusterMasterBaseHandler):
    def get(self):
        # all arguments are optional, so default to None
        since_timestamp = self.get_query_argument('since_timestamp', None)
        since_id = self.get_query_argument('since_id', None)
        self.write({
            'events': analytics.get_events(since_timestamp, since_id),
        })
