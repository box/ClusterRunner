from collections import OrderedDict
import os

from app.common.cluster_service import ClusterService
from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.build_request_handler import BuildRequestHandler
from app.master.build_scheduler_pool import BuildSchedulerPool
from app.master.slave import Slave
from app.master.slave_allocator import SlaveAllocator
from app.slave.cluster_slave import SlaveState
from app.util.conf.configuration import Configuration
from app.util.exceptions import BadRequestError, ItemNotFoundError, ItemNotReadyError
from app.util import fs
from app.util.log import get_logger


class ClusterMaster(ClusterService):
    """
    The ClusterRunner Master service: This is the main application class that the web framework/REST API sits on top of.
    """

    API_VERSION = 'v1'

    def __init__(self):
        self._logger = get_logger(__name__)
        self._master_results_path = Configuration['results_directory']
        self._all_slaves_by_url = {}
        self._all_builds_by_id = OrderedDict()
        self._scheduler_pool = BuildSchedulerPool()
        self._build_request_handler = BuildRequestHandler(self._scheduler_pool)
        self._build_request_handler.start()
        self._slave_allocator = SlaveAllocator(self._scheduler_pool)
        self._slave_allocator.start()

        # Asynchronously delete (but immediately rename) all old builds when master starts.
        # Remove this if/when build numbers are unique across master starts/stops
        if os.path.exists(self._master_results_path):
            fs.async_delete(self._master_results_path)

        fs.create_dir(self._master_results_path)

    def _get_status(self):
        """
        Just returns a dumb message and prints it to the console.

        :rtype: str
        """
        return 'Master service is up.'

    def api_representation(self):
        """
        Gets a dict representing this resource which can be returned in an API response.
        :rtype: dict [str, mixed]
        """
        slaves_representation = [slave.api_representation() for slave in self.all_slaves_by_id().values()]
        return {
            'status': self._get_status(),
            'slaves': slaves_representation,
        }

    def builds(self):
        """
        Returns a list of all builds
        :rtype: list[Build]
        """
        return self._all_builds_by_id.values()

    def active_builds(self):
        """
        Returns a list of incomplete builds
        :rtype: list[Build]
        """
        return [build for build in self.builds() if not build.is_finished]

    def all_slaves_by_id(self):
        """
        Retrieve all connected slaves
        :rtype: dict [int, Slave]
        """
        slaves_by_slave_id = {}
        for slave in self._all_slaves_by_url.values():
            slaves_by_slave_id[slave.id] = slave
        return slaves_by_slave_id

    def get_slave(self, slave_id=None, slave_url=None):
        """
        Get the instance of given slave by either the slave's id or url. Only one of slave_id or slave_url should be
        specified.

        :param slave_id: The id of the slave to return
        :type slave_id: int
        :param slave_url: The url of the slave to return
        :type slave_url: str
        :return: The instance of the slave
        :rtype: Slave
        """
        if (slave_id is None) == (slave_url is None):
            raise ValueError('Only one of slave_id or slave_url should be specified to get_slave().')

        if slave_id is not None:
            for slave in self._all_slaves_by_url.values():
                if slave.id == slave_id:
                    return slave
        else:
            if slave_url in self._all_slaves_by_url:
                return self._all_slaves_by_url[slave_url]

        raise ItemNotFoundError('Requested slave ({}) does not exist.'.format(slave_id))

    def connect_slave(self, slave_url, num_executors, slave_session_id=None):
        """
        Connect a slave to this master.

        :type slave_url: str
        :type num_executors: int
        :type slave_session_id: str | None
        :return: The response with the slave id of the slave.
        :rtype: dict[str, str]
        """
        # todo: Validate arg types for this and other methods called via API.
        # If a slave had previously been connected, and is now being reconnected, the cleanest way to resolve this
        # bookkeeping is for the master to forget about the previous slave instance and start with a fresh instance.
        if slave_url in self._all_slaves_by_url:
            old_slave = self._all_slaves_by_url.get(slave_url)
            self._logger.warning('Slave requested to connect to master, even though previously connected as {}. ' +
                                 'Removing existing slave instance from the master\'s bookkeeping.', old_slave)

            # If a slave has requested to reconnect, we have to assume that whatever build the dead slave was
            # working on no longer has valid results.
            if old_slave.current_build_id is not None:
                self._logger.info('{} has build [{}] running on it. Attempting to cancel build.', old_slave,
                                  old_slave.current_build_id)
                try:
                    build = self.get_build(old_slave.current_build_id)
                    build.cancel()
                    self._logger.info('Cancelled build {} due to dead slave {}', old_slave.current_build_id,
                                      old_slave)
                except ItemNotFoundError:
                    self._logger.info('Failed to find build {} that was running on {}', old_slave.current_build_id,
                                      old_slave)

        slave = Slave(slave_url, num_executors, slave_session_id)
        self._all_slaves_by_url[slave_url] = slave
        self._slave_allocator.add_idle_slave(slave)
        self._logger.info('Slave on {} connected to master with {} executors. (id: {})',
                          slave_url, num_executors, slave.id)
        return {'slave_id': str(slave.id)}

    def handle_slave_state_update(self, slave, new_slave_state):
        """
        Execute logic to transition the specified slave to the given state.

        :type slave: Slave
        :type new_slave_state: SlaveState
        """
        slave_transition_functions = {
            SlaveState.DISCONNECTED: self._disconnect_slave,
            SlaveState.SHUTDOWN: self._graceful_shutdown_slave,
            SlaveState.IDLE: self._slave_allocator.add_idle_slave,
            SlaveState.SETUP_COMPLETED: self._handle_setup_success_on_slave,
            SlaveState.SETUP_FAILED: self._handle_setup_failure_on_slave,
        }

        if new_slave_state not in slave_transition_functions:
            raise BadRequestError('Invalid slave state "{}". Valid states are: {}.'
                                  .format(new_slave_state, ', '.join(slave_transition_functions.keys())))

        do_transition = slave_transition_functions.get(new_slave_state)
        do_transition(slave)

    def set_shutdown_mode_on_slaves(self, slave_ids):
        """
        :type slave_ids: list[int]
        """
        # Find all the slaves first so if an invalid slave_id is specified, we 404 before shutting any of them down.
        slaves = [self.get_slave(slave_id) for slave_id in slave_ids]
        for slave in slaves:
            self.handle_slave_state_update(slave, SlaveState.SHUTDOWN)

    def _graceful_shutdown_slave(self, slave):
        """
        Puts slave in shutdown mode so it cannot receive new builds. The slave will be killed when finished with any
        running builds.
        :type slave: Slave
        """
        slave.set_shutdown_mode()
        self._logger.info('Slave on {} was put in shutdown mode. (id: {})', slave.url, slave.id)

    def _disconnect_slave(self, slave):
        """
        Mark a slave dead.

        :type slave: Slave
        """
        # Mark slave dead. We do not remove it from the list of all slaves. We also do not remove it from idle_slaves;
        # that will happen during slave allocation.
        slave.mark_dead()
        # todo: Fail/resend any currently executing subjobs still executing on this slave.
        self._logger.info('Slave on {} was disconnected. (id: {})', slave.url, slave.id)

    def _handle_setup_success_on_slave(self, slave):
        """
        Respond to successful build setup on a slave. This starts subjob executions on the slave. This should be called
        once after the specified slave has already run build_setup commands for the specified build.

        :type slave: Slave
        """
        build = self.get_build(slave.current_build_id)
        scheduler = self._scheduler_pool.get(build)
        scheduler.begin_subjob_executions_on_slave(slave)

    def _handle_setup_failure_on_slave(self, slave):
        """
        Respond to failed build setup on a slave. This should put the slave back into a usable state.

        :type slave: Slave
        """
        raise BadRequestError('Setup failure handling on the master is not yet implemented.')

    def handle_request_for_new_build(self, build_params):
        """
        Creates a new Build object and adds it to the request queue to be processed.

        :param build_params:
        :type build_params: dict[str, str]
        :rtype tuple [bool, dict [str, str]]
        """
        build_request = BuildRequest(build_params)
        success = False

        if build_request.is_valid():
            build = Build(build_request)
            self._all_builds_by_id[build.build_id()] = build
            build.generate_project_type()  # WIP(joey): This should be internal to the Build object.
            self._build_request_handler.handle_build_request(build)
            response = {'build_id': build.build_id()}
            success = True
        elif not build_request.is_valid_type():
            response = {'error': 'Invalid build request type.'}
        else:
            required_params = build_request.required_parameters()
            response = {'error': 'Missing required parameter. Required parameters: {}'.format(required_params)}

        return success, response  # todo: refactor to use exception instead of boolean

    def handle_request_to_update_build(self, build_id, update_params):
        """
        Updates the state of a build with the values passed in.  Used for cancelling running builds.

        :type build_id: int
        :param update_params: The fields that should be updated and their new values
        :type update_params: dict [str, str]
        :return: The success/failure and the response we want to send to the requestor
        :rtype: tuple [bool, dict [str, str]]
        """
        build = self._all_builds_by_id.get(int(build_id))
        if build is None:
            raise ItemNotFoundError('Invalid build id.')

        success, response = build.validate_update_params(update_params)
        if not success:
            return success, response
        return build.update_state(update_params), {}

    def handle_result_reported_from_slave(self, slave_url, build_id, subjob_id, payload=None):
        """
        Process the result and dispatch the next subjob
        :type slave_url: str
        :type build_id: int
        :type subjob_id: int
        :type payload: dict
        :rtype: str
        """
        self._logger.info('Results received from {} for subjob. (Build {}, Subjob {})', slave_url, build_id, subjob_id)
        build = self._all_builds_by_id[int(build_id)]
        slave = self._all_slaves_by_url[slave_url]
        # If the build has been canceled, don't work on the next subjob.
        if not build.is_finished:  # WIP(joey): This check should be internal to the Build object.
            try:
                build.complete_subjob(subjob_id, payload)
            finally:
                scheduler = self._scheduler_pool.get(build)
                scheduler.execute_next_subjob_or_free_executor(slave)

    def get_build(self, build_id):
        """
        Returns a build by id
        :param build_id: The id for the build whose status we are getting
        :type build_id: int
        :rtype: Build
        """
        build = self._all_builds_by_id.get(build_id)
        if build is None:
            raise ItemNotFoundError('Invalid build id: {}.'.format(build_id))

        return build

    def get_path_for_build_results_archive(self, build_id):
        """
        Given a build id, get the absolute file path for the archive file containing the build results.

        :param build_id: The build id for which to retrieve the artifacts archive file
        :type build_id: int
        :return: The path to the archived results file
        :rtype: str
        """
        build = self._all_builds_by_id.get(build_id)
        if build is None:
            raise ItemNotFoundError('Invalid build id.')

        archive_file = build.artifacts_archive_file
        if archive_file is None:
            raise ItemNotReadyError('Build artifact file is not yet ready. Try again later.')

        return archive_file
