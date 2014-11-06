import http.client
from queue import Queue
import sys
from threading import Event
import requests

from app.slave.subjob_executor import SubjobExecutor
from app.util import analytics, log, util
from app.util.exceptions import BadRequestError
from app.util.network import Network
from app.util.safe_thread import SafeThread
from app.util.unhandled_exception_handler import UnhandledExceptionHandler
from app.util.url_builder import UrlBuilder


class ClusterSlave(object):

    API_VERSION = 'v1'

    def __init__(self, port, host, num_executors=10):
        """
        :param port: The port number the slave service is running on
        :type port: int
        :param host: The hostname at which the slave is reachable
        :type host: str
        :param num_executors: The number of executors this slave should operate with -- this determines how many
            concurrent subjobs the slave can execute.
        :type num_executors: int
        """
        self.port = port
        self.host = host
        self._slave_id = None
        self._num_executors = num_executors
        self._logger = log.get_logger(__name__)

        self._idle_executors = Queue(maxsize=num_executors)
        self.executors = {}
        for executor_id in range(num_executors):
            executor = SubjobExecutor(executor_id)
            self._idle_executors.put(executor)
            self.executors[executor_id] = executor

        self._setup_complete_event = Event()
        self._master_url = None
        self._network = Network(min_connection_poolsize=num_executors)
        self._master_api = None  # wait until we connect to a master first

        self._project_type = None  # this will be instantiated during build setup
        self._current_build_id = None

        UnhandledExceptionHandler.singleton().add_teardown_callback(self._async_teardown_build,
                                                                    should_disconnect_from_master=True)

    def api_representation(self):
        """
        Gets a dict representing this resource which can be returned in an API response.
        :rtype: dict [str, mixed]
        """
        executors_representation = [executor.api_representation() for executor in self.executors.values()]
        return {
            'connected': str(self._is_connected()),
            'master_url': self._master_url,
            'setup_complete': str(self._setup_complete_event.isSet()),
            'slave_id': self._slave_id,
            'executors': executors_representation,
        }

    def _is_connected(self):
        return self._master_url is not None

    def get_status(self):
        """
        Just returns a dumb message and prints it to the console.
        """
        return 'Slave service is up. <Port: {}>'.format(self.port)

    def setup_build(self, build_id, project_type_params):
        """
        Usually called once per build to do build-specific setup. Will block any subjobs from executing until setup
        completes. The actual setup is performed on another thread and will unblock subjobs (via an Event) once it
        finishes.

        :param build_id: The id of the build to run setup on
        :type build_id: int
        :param project_type_params: The parameters that define the project_type this build will execute in
        :type project_type_params: dict
        """
        self._logger.info('Executing setup for build {} (type: {}).', build_id, project_type_params.get('type'))
        self._setup_complete_event.clear()
        self._current_build_id = build_id

        # create an project_type instance for build-level operations
        self._project_type = util.create_project_type(project_type_params)

        # verify all executors are idle
        if not self._idle_executors.full():
            raise RuntimeError('Slave tried to setup build but not all executors are idle. ({}/{} executors idle.)'
                               .format(self._idle_executors.qsize(), self._num_executors))

        # Collect all the executors to pass to project_type.setup_build(). This will create a new project_type for
        # each executor (for subjob-level operations).
        executors = list(self._idle_executors.queue)
        SafeThread(target=self._async_setup_build, args=(executors, project_type_params)).start()

    def _async_setup_build(self, executors, project_type_params):
        """
        Called from setup_build(). Do asynchronous setup for the build so that we can make the call to setup_build()
        non-blocking.
        """
        # todo(joey): It's strange that the project_type is setting up the executors, which in turn set up projects.
        # todo(joey): I think this can be untangled a bit -- we should call executor.configure_project_type() here.
        self._project_type.setup_build(executors, project_type_params)

        self._logger.info('Build setup complete for build {}.', self._current_build_id)
        self._setup_complete_event.set()  # free any subjob threads that are waiting for setup to complete

    def teardown_build(self, build_id=None):
        """
        Called at the end of each build on each slave before it reports back to the master that it is idle again.

        :param build_id: The build id to teardown -- this parameter is used solely for correctness checking of the
            master, to make sure that the master is not erroneously sending teardown commands for other builds.
        :type build_id: int | None
        """
        if self._current_build_id is None:
            raise BadRequestError('Tried to teardown a build but no build is active on this slave.')

        if build_id is not None and build_id != self._current_build_id:
            raise BadRequestError('Tried to teardown build {}, '
                                  'but slave is running build {}!'.format(build_id, self._current_build_id))

        self._logger.info('Executing teardown for build {}.', self._current_build_id)

        SafeThread(target=self._async_teardown_build).start()

    def _async_teardown_build(self, should_disconnect_from_master=False):
        """
        Called from teardown_build(). Do asynchronous teardown for the build so that we can make the call to
        teardown_build() non-blocking. Also take care of posting back to the master when teardown is complete.
        """
        # Kill all executors' processes. This only has an effect if we are tearing down before a build completes.
        for executor in self.executors.values():
            executor.kill()

        if self._project_type:
            self._project_type.teardown_build()
            self._logger.info('Build teardown complete for build {}.', self._current_build_id)
            self._current_build_id = None
            self._project_type = None

        if not should_disconnect_from_master:
            # report back to master that this slave is finished with teardown and ready for a new build
            self._logger.info('Notifying master that this slave is ready for new builds.')
            idle_url = self._master_api.url('slave', self._slave_id, 'idle')
            response = self._network.post(idle_url)
            if response.status_code != http.client.OK:
                raise RuntimeError("Could not post teardown completion to master at {}".format(idle_url))

        elif self._is_master_responsive():
            # report back to master that this slave is shutting down and should not receive new builds
            self._logger.info('Notifying master to disconnect this slave.')
            disconnect_url = self._master_api.url('slave', self._slave_id, 'disconnect')
            response = self._network.post(disconnect_url)
            if response.status_code != http.client.OK:
                self._logger.error('Could not post disconnect notification to master at {}'.format(disconnect_url))

    def connect_to_master(self, master_url=None):
        """
        Notify the master that this slave exists.

        :param master_url: The URL of the master service. If none specified, defaults to localhost:43000.
        :type master_url: str
        """
        self._master_url = master_url or 'localhost:43000'
        self._master_api = UrlBuilder(self._master_url)
        connect_url = self._master_api.url('slave')
        data = {
            'slave': '{}:{}'.format(self.host, self.port),
            'num_executors': self._num_executors,
        }
        response = self._network.post(connect_url, data)
        self._slave_id = int(response.json().get('slave_id'))
        self._logger.info('Slave {}:{} connected to master on {}.', self.host, self.port, self._master_url)

    def _is_master_responsive(self):
        """
        Ping the master to check if it is still alive. Code using this method should treat the return value as a
        *probable* truth since the state of the master can change at any time. This method is not a replacement for
        error handling.

        :return: Whether the master is responsive or not
        :rtype: bool
        """
        # todo: This method repeats some logic we have in the deployment code (checking a service). We should DRY it up.
        is_responsive = True
        try:
            self._network.get(self._master_api.url())
        except requests.ConnectionError:
            is_responsive = False

        return is_responsive

    def start_working_on_subjob(self, build_id, subjob_id, subjob_artifact_dir, atomic_commands):
        """
        Begin working on a subjob with the given build id and subjob id. This just starts the subjob execution
        asynchronously on a separate thread.

        :type build_id: int
        :type subjob_id: int
        :type subjob_artifact_dir: str
        :type atomic_commands: list[str]
        :return: The text to return in the API response.
        :rtype: dict[str, int]
        """
        if build_id != self._current_build_id:
            raise BadRequestError('Attempted to start subjob {} for build {}, '
                                  'but current build id is {}.'.format(subjob_id, build_id, self._current_build_id))

        # get idle executor from queue to claim it as in-use (or block until one is available)
        executor = self._idle_executors.get()

        # Start a thread to execute the job (after waiting for setup to complete)
        SafeThread(
            target=self._execute_subjob,
            args=(build_id, subjob_id, executor, subjob_artifact_dir, atomic_commands),
            name='Build{}-Sub{}'.format(build_id, subjob_id),
        ).start()

        self._logger.info('Slave ({}:{}) has received subjob. (Build {}, Subjob {})', self.host, self.port, build_id,
                          subjob_id)
        return {'executor_id': executor.id}

    def _execute_subjob(self, build_id, subjob_id, executor, subjob_artifact_dir, atomic_commands):
        """
        This is the method for executing a subjob asynchronously. This performs the work required by executing the
        specified command, then does a post back to the master results endpoint to signal that the work is done.

        :type build_id: int
        :type subjob_id: int
        :type executor: SubjobExecutor
        :type subjob_artifact_dir: str
        :type atomic_commands: list[str]
        """
        self._logger.debug('Waiting for setup to complete (Build {}, Subjob {})...', build_id, subjob_id)
        self._setup_complete_event.wait()  # block until setup completes
        subjob_event_data = {'build_id': build_id, 'subjob_id': subjob_id, 'executor_id': executor.id}

        analytics.record_event(analytics.SUBJOB_EXECUTION_START, **subjob_event_data)
        results_file = executor.execute_subjob(build_id, subjob_id, subjob_artifact_dir, atomic_commands)
        analytics.record_event(analytics.SUBJOB_EXECUTION_FINISH, **subjob_event_data)

        results_url = self._master_api.url('build', build_id, 'subjob', subjob_id, 'result')
        data = {
            'slave': '{}:{}'.format(self.host, self.port),
            'metric_data': {'executor_id': executor.id},
        }
        files = {'file': ('payload', open(results_file, 'rb'), 'application/x-compressed')}

        self._idle_executors.put(executor)  # work is done; mark executor as idle
        self._network.post(results_url, data=data, files=files)  # todo: check return code

        self._logger.info('Build {}, Subjob {} completed and sent results to master.', build_id, subjob_id)

    def kill(self):
        # TODO(dtran): Kill the threads and this server more gracefully
        sys.exit(0)
