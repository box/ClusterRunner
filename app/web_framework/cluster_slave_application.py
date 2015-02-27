from app.util import analytics
from app.util.conf.configuration import Configuration
from app.util.decorators import authenticated
from app.util.safe_thread import SafeThread
from app.web_framework.cluster_application import ClusterApplication
from app.web_framework.cluster_base_handler import ClusterBaseHandler
from app.web_framework.route_node import RouteNode


class ClusterSlaveApplication(ClusterApplication):

    def __init__(self, cluster_slave):
        """
        :type cluster_slave: ClusterSlave
        """
        default_params = {
            'cluster_slave': cluster_slave
        }
        # The routes are described using a tree structure.  This is a better representation of a path than a flat list
        #  of strings and allows us to inspect children/parents of a node to generate 'child routes'
        root_route = \
            RouteNode(r'/', _RootHandler).add_children([
                RouteNode(r'v1', _APIVersionOneHandler).add_children([
                    RouteNode(r'version', _VersionHandler),
                    RouteNode(r'build', _BuildsHandler, 'builds').add_children([
                        RouteNode(r'(\d+)', _BuildHandler, 'build').add_children([
                            RouteNode(r'setup', _BuildSetupHandler),
                            RouteNode(r'teardown', _TeardownHandler),
                            RouteNode(r'subjob', _SubjobsHandler, 'subjobs').add_children([
                                RouteNode(r'(\d+)', _SubjobHandler, 'subjob')
                            ])
                        ])
                    ]),
                    RouteNode(r'executor', _ExecutorsHandler, 'executors').add_children([
                        RouteNode(r'(\d+)', _ExecutorHandler, 'executor')
                    ]),
                    RouteNode(r'eventlog', _EventlogHandler),
                    RouteNode(r'kill', _KillHandler)
                ])
            ])
        handlers = self.get_all_handlers(root_route, default_params)
        super().__init__(handlers)


class _ClusterSlaveBaseHandler(ClusterBaseHandler):
    def initialize(self, route_node=None, cluster_slave=None):
        """
        :type route_node: RouteNode | None
        :type cluster_slave: ClusterSlave | None
        """
        self._cluster_slave = cluster_slave
        super().initialize(route_node)


class _RootHandler(_ClusterSlaveBaseHandler):
    pass


class _APIVersionOneHandler(_ClusterSlaveBaseHandler):
    def get(self):
        response = {
            'slave': self._cluster_slave.api_representation(),
        }
        self.write(response)


class _VersionHandler(_ClusterSlaveBaseHandler):
    def get(self):
        response = {
            'version': Configuration['version'],
        }
        self.write(response)


class _BuildsHandler(_ClusterSlaveBaseHandler):
    pass


class _BuildHandler(_ClusterSlaveBaseHandler):
    pass


class _BuildSetupHandler(_ClusterSlaveBaseHandler):
    @authenticated
    def post(self, build_id):
        project_type_params = self.decoded_body.get('project_type_params')
        build_executor_start_index = self.decoded_body.get('build_executor_start_index')
        self._cluster_slave.setup_build(int(build_id), project_type_params, int(build_executor_start_index))
        self._write_status()


class _TeardownHandler(_ClusterSlaveBaseHandler):
    def post(self, build_id):
        self._cluster_slave.teardown_build(int(build_id))
        self._write_status()


class _SubjobsHandler(_ClusterSlaveBaseHandler):
    pass


class _SubjobHandler(_ClusterSlaveBaseHandler):
    @authenticated
    def post(self, build_id, subjob_id):
        subjob_artifact_dir = self.decoded_body.get('subjob_artifact_dir')
        atomic_commands = self.decoded_body.get('atomic_commands')

        response = self._cluster_slave.start_working_on_subjob(
            int(build_id), int(subjob_id), subjob_artifact_dir, atomic_commands
        )
        self._write_status(response, status_code=201)

    def get(self, build_id, subjob_id):
        response = {
            'comment': 'not implemented',
        }
        self.write(response)


class _ExecutorsHandler(_ClusterSlaveBaseHandler):
    def get(self):
        response = {
            'executors': [executor.api_representation() for executor in self._cluster_slave.executors_by_id.values()]
        }
        self.write(response)


class _ExecutorHandler(_ClusterSlaveBaseHandler):
    def get(self, executor_id):
        executor = self._cluster_slave.executors_by_id[int(executor_id)]
        response = {
            'executor': executor.api_representation()
        }
        self.write(response)


class _EventlogHandler(_ClusterSlaveBaseHandler):
    def get(self):
        # all arguments are optional, so default to None
        since_timestamp = self.get_query_argument('since_timestamp', None)
        since_id = self.get_query_argument('since_id', None)
        self.write({
            'events': analytics.get_events(since_timestamp, since_id),
        })


class _KillHandler(_ClusterSlaveBaseHandler):
    def post(self):
        self._write_status()
        kill_thread = SafeThread(
            name='kill-thread',
            target=self._cluster_slave.kill,
        )
        kill_thread.start()
