from app.util import analytics
from app.util.conf.configuration import Configuration
from app.util.decorators import authenticated
from app.util.safe_thread import SafeThread
from app.web_framework.cluster_application import ClusterApplication
from app.web_framework.cluster_base_handler import ClusterBaseAPIHandler
from app.web_framework.route_node import RouteNode


class ClusterWorkerApplication(ClusterApplication):

    def __init__(self, cluster_worker):
        """
        :type cluster_worker: ClusterWorker
        """
        default_params = {
            'cluster_worker': cluster_worker
        }
        # The routes are described using a tree structure.  This is a better representation of a path than a flat list
        #  of strings and allows us to inspect children/parents of a node to generate 'child routes'
        api_v1 = [
            RouteNode(r'v1', _APIVersionOneHandler).add_children([
                RouteNode(r'version', _VersionHandler),
                RouteNode(r'build', _BuildsHandler, 'builds').add_children([
                    RouteNode(r'(\d+)', _BuildHandler, 'build').add_children([
                        RouteNode(r'setup', _BuildSetupHandler),
                        RouteNode(r'teardown', _TeardownHandler),
                        RouteNode(r'subjob', _SubjobsHandler, 'subjobs').add_children([
                            RouteNode(r'(\d+)', _SubjobHandler, 'subjob').add_children([
                                RouteNode(r'atom', _AtomsHandler, 'atoms').add_children([
                                    RouteNode(r'(\d+)', _AtomHandler).add_children([
                                        RouteNode(r'console', _AtomConsoleHandler)
                                    ])
                                ])
                            ])
                        ])
                    ])
                ]),
                RouteNode(r'executor', _ExecutorsHandler, 'executors').add_children([
                    RouteNode(r'(\d+)', _ExecutorHandler, 'executor')
                ]),
                RouteNode(r'eventlog', _EventlogHandler),
                RouteNode(r'kill', _KillHandler)
            ])]

        api_v2 = [
            RouteNode(r'version', _VersionHandler),
            RouteNode(r'builds', _BuildsHandler, 'builds').add_children([
                RouteNode(r'(\d+)', _BuildHandler, 'build').add_children([
                    RouteNode(r'setup', _BuildSetupHandler),
                    RouteNode(r'teardown', _TeardownHandler),
                    RouteNode(r'subjobs', _SubjobsHandler, 'subjobs').add_children([
                        RouteNode(r'(\d+)', _SubjobHandler, 'subjob').add_children([
                            RouteNode(r'atoms', _AtomsHandler, 'atoms').add_children([
                                RouteNode(r'(\d+)', _AtomHandler).add_children([
                                    RouteNode(r'console', _AtomConsoleHandler)
                                ])
                            ])
                        ])
                    ])
                ])
            ]),
            RouteNode(r'executor', _ExecutorsHandler, 'executors').add_children([
                RouteNode(r'(\d+)', _ExecutorHandler, 'executor')
            ]),
            RouteNode(r'eventlog', _EventlogHandler),
            RouteNode(r'kill', _KillHandler)]

        root = RouteNode(r'/', _RootHandler)
        root.add_children(api_v1, version=1)
        root.add_children(api_v2, version=2)

        handlers = self.get_all_handlers(root, default_params)
        super().__init__(handlers)


class _ClusterWorkerBaseAPIHandler(ClusterBaseAPIHandler):
    def initialize(self, route_node=None, cluster_worker=None):
        """
        :type route_node: RouteNode | None
        :type cluster_worker: ClusterWorker | None
        """
        self._cluster_worker = cluster_worker
        super().initialize(route_node)


class _RootHandler(_ClusterWorkerBaseAPIHandler):
    pass


class _APIVersionOneHandler(_ClusterWorkerBaseAPIHandler):
    def get(self):
        response = {
            'worker': self._cluster_worker.api_representation(),
        }
        self.write(response)


class _VersionHandler(_ClusterWorkerBaseAPIHandler):
    def get(self):
        response = {
            'version': Configuration['version'],
            'api_version': self.api_version,
        }
        self.write(response)


class _BuildsHandler(_ClusterWorkerBaseAPIHandler):
    pass


class _BuildHandler(_ClusterWorkerBaseAPIHandler):
    pass


class _BuildSetupHandler(_ClusterWorkerBaseAPIHandler):
    @authenticated
    def post(self, build_id):
        project_type_params = self.decoded_body.get('project_type_params')
        build_executor_start_index = self.decoded_body.get('build_executor_start_index')
        self._cluster_worker.setup_build(int(build_id), project_type_params, int(build_executor_start_index))
        self._write_status()


class _TeardownHandler(_ClusterWorkerBaseAPIHandler):
    def post(self, build_id):
        self._cluster_worker.teardown_build(int(build_id))
        self._write_status()


class _SubjobsHandler(_ClusterWorkerBaseAPIHandler):
    pass


class _SubjobHandler(_ClusterWorkerBaseAPIHandler):
    @authenticated
    def post(self, build_id, subjob_id):
        atomic_commands = self.decoded_body.get('atomic_commands')

        response = self._cluster_worker.start_working_on_subjob(
            int(build_id), int(subjob_id), atomic_commands
        )
        self._write_status(response, status_code=201)

    def get(self, build_id, subjob_id):
        response = {
            'comment': 'not implemented',
        }
        self.write(response)


class _AtomsHandler(_ClusterWorkerBaseAPIHandler):
    pass


class _AtomHandler(_ClusterWorkerBaseAPIHandler):
    pass


class _AtomConsoleHandler(_ClusterWorkerBaseAPIHandler):
    def get(self, build_id, subjob_id, atom_id):
        """
        :type build_id: int
        :type subjob_id: int
        :type atom_id: int
        """
        # Because the 'Origin' header in the redirect (from the manager) gets set to 'null', the only way
        # for the client to receive this response is for us to allow any origin to receive this response.
        self.set_header('Access-Control-Allow-Origin', '*')

        max_lines = int(self.get_query_argument('max_lines', 50))
        offset_line = self.get_query_argument('offset_line', None)

        if offset_line is not None:
            offset_line = int(offset_line)

        response = self._cluster_worker.get_console_output(
            build_id,
            subjob_id,
            atom_id,
            Configuration['artifact_directory'],
            max_lines,
            offset_line
        )
        self.write(response)


class _ExecutorsHandler(_ClusterWorkerBaseAPIHandler):
    def get(self):
        response = {
            'executors': [executor.api_representation() for executor in self._cluster_worker.executors_by_id.values()]
        }
        self.write(response)


class _ExecutorHandler(_ClusterWorkerBaseAPIHandler):
    def get(self, executor_id):
        executor = self._cluster_worker.executors_by_id[int(executor_id)]
        response = {
            'executor': executor.api_representation()
        }
        self.write(response)


class _EventlogHandler(_ClusterWorkerBaseAPIHandler):
    def get(self):
        # all arguments are optional, so default to None
        since_timestamp = self.get_query_argument('since_timestamp', None)
        since_id = self.get_query_argument('since_id', None)
        self.write({
            'events': analytics.get_events(since_timestamp, since_id),
        })


class _KillHandler(_ClusterWorkerBaseAPIHandler):
    @authenticated
    def post(self):
        self._write_status()
        kill_thread = SafeThread(
            name='kill-thread',
            target=self._cluster_worker.kill,
        )
        kill_thread.start()
