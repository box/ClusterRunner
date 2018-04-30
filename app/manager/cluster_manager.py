from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import sched
from threading import Thread
from typing import List

from app.common.cluster_service import ClusterService
from app.common.metrics import WorkersCollector
from app.manager.build import Build, MAX_SETUP_FAILURES
from app.manager.build_request import BuildRequest
from app.manager.build_request_handler import BuildRequestHandler
from app.manager.build_scheduler_pool import BuildSchedulerPool
from app.manager.build_store import BuildStore
from app.manager.worker import Worker, WorkerRegistry
from app.manager.worker_allocator import WorkerAllocator
from app.worker.cluster_worker import WorkerState
from app.worker.cluster_worker import ClusterWorker
from app.util import fs
from app.util.conf.configuration import Configuration
from app.util.exceptions import BadRequestError, ItemNotFoundError, ItemNotReadyError
from app.util.log import get_logger
from app.util.pagination import get_paginated_indices


class ClusterManager(ClusterService):
    """
    The ClusterRunner Manager service: This is the main application class that the web framework/REST API sits on top of.
    """

    API_VERSION = 'v1'

    def __init__(self):
        self._logger = get_logger(__name__)
        self._manager_results_path = Configuration['results_directory']
        self._worker_registry = WorkerRegistry.singleton()
        self._scheduler_pool = BuildSchedulerPool()
        self._build_request_handler = BuildRequestHandler(self._scheduler_pool)
        self._build_request_handler.start()
        self._worker_allocator = WorkerAllocator(self._scheduler_pool)
        self._worker_allocator.start()

        # The best practice for determining the number of threads to use is
        # the number of threads per core multiplied by the number of physical
        # cores. So for example, with 10 cores, 2 sockets and 2 per core, the
        # max would be 40.
        #
        # Currently we use threads for incrementing/decrementing worker executor
        # counts (lock acquisition) and tearing down the worker (network IO). 32 threads should be
        # plenty for these tasks. In the case of heavy load, the bottle neck will be the number
        # of executors, not the time it takes to lock/unlock the executor counts or the number of
        # teardown requests. Tweak the number to find the sweet spot if you feel this is the case.
        self._thread_pool_executor = ThreadPoolExecutor(max_workers=32)

        # Asynchronously delete (but immediately rename) all old builds when manager starts.
        # Remove this if/when build numbers are unique across manager starts/stops
        if os.path.exists(self._manager_results_path):
            fs.async_delete(self._manager_results_path)
        fs.create_dir(self._manager_results_path)

        # Configure heartbeat tracking
        self._unresponsive_workers_cleanup_interval = Configuration['unresponsive_workers_cleanup_interval']
        self._hb_scheduler = sched.scheduler()

        WorkersCollector.register_workers_metrics_collector(lambda: self._worker_registry.get_all_workers_by_id().values())

    def start_heartbeat_tracker_thread(self):
        self._logger.info('Heartbeat tracker will run every {} seconds'.format(
            self._unresponsive_workers_cleanup_interval))
        Thread(target=self._start_heartbeat_tracker, name='HeartbeatTrackerThread', daemon=True).start()

    def _start_heartbeat_tracker(self):
        self._hb_scheduler.enter(0, 0, self._disconnect_non_heartbeating_workers)
        self._hb_scheduler.run()

    def _disconnect_non_heartbeating_workers(self):
        workers_to_disconnect = [worker for worker in self._worker_registry.get_all_workers_by_url().values()
                                 if worker.is_alive() and not self._is_worker_responsive(worker)]

        for worker in workers_to_disconnect:
            self._disconnect_worker(worker)
            self._logger.error('Worker {} marked offline as it is not sending heartbeats.'.format(
                worker.id))

        self._hb_scheduler.enter(self._unresponsive_workers_cleanup_interval, 0,
                                 self._disconnect_non_heartbeating_workers)

    def _is_worker_responsive(self, worker: ClusterWorker) -> bool:
        time_since_last_heartbeat = (datetime.now() - worker.get_last_heartbeat_time()).seconds
        return time_since_last_heartbeat < self._unresponsive_workers_cleanup_interval

    def _get_status(self):
        """
        Just returns a dumb message and prints it to the console.

        :rtype: str
        """
        return 'Manager service is up.'

    def api_representation(self):
        """
        Gets a dict representing this resource which can be returned in an API response.
        :rtype: dict [str, mixed]
        """
        workers_representation = [worker.api_representation() for worker in
                                  self._worker_registry.get_all_workers_by_id().values()]
        return {
            'status': self._get_status(),
            'workers': workers_representation,
        }

    def get_builds(self, offset: int=None, limit: int=None) -> List['Build']:
        """
        Returns a list of all builds.
        :param offset: The starting index of the requested build
        :param limit: The number of builds requested
        """
        num_builds = BuildStore.size()
        start, end = get_paginated_indices(offset, limit, num_builds)
        return BuildStore.get_range(start, end)

    def active_builds(self):
        """
        Returns a list of incomplete builds
        :rtype: list[Build]
        """
        return [build for build in self.get_builds() if not build.is_finished]

    def connect_worker(self, worker_url, num_executors, worker_session_id=None):
        """
        Connect a worker to this manager.

        :type worker_url: str
        :type num_executors: int
        :type worker_session_id: str | None
        :return: The response with the worker id of the worker.
        :rtype: dict[str, str]
        """
        # todo: Validate arg types for this and other methods called via API.
        # If a worker had previously been connected, and is now being reconnected, the cleanest way to resolve this
        # bookkeeping is for the manager to forget about the previous worker instance and start with a fresh instance.
        try:
            old_worker = self._worker_registry.get_worker(worker_url=worker_url)
        except ItemNotFoundError:
            pass
        else:
            self._logger.warning('Worker requested to connect to manager, even though previously connected as {}. ' +
                                 'Removing existing worker instance from the manager\'s bookkeeping.', old_worker)
            # If a worker has requested to reconnect, we have to assume that whatever build the dead worker was
            # working on no longer has valid results.
            if old_worker.current_build_id is not None:
                self._logger.info('{} has build [{}] running on it. Attempting to cancel build.', old_worker,
                                  old_worker.current_build_id)
                try:
                    build = self.get_build(old_worker.current_build_id)
                    build.cancel()
                    self._logger.info('Cancelled build {} due to dead worker {}', old_worker.current_build_id,
                                      old_worker)
                except ItemNotFoundError:
                    self._logger.info('Failed to find build {} that was running on {}', old_worker.current_build_id,
                                      old_worker)

        worker = Worker(worker_url, num_executors, worker_session_id)
        self._worker_registry.add_worker(worker)
        self._worker_allocator.add_idle_worker(worker)
        self._logger.info('Worker on {} connected to manager with {} executors. (id: {})',
                          worker_url, num_executors, worker.id)
        return {'worker_id': str(worker.id)}

    def handle_worker_state_update(self, worker, new_worker_state):
        """
        Execute logic to transition the specified worker to the given state.

        :type worker: Worker
        :type new_worker_state: WorkerState
        """
        worker_transition_functions = {
            WorkerState.DISCONNECTED: self._disconnect_worker,
            WorkerState.SHUTDOWN: self._graceful_shutdown_worker,
            WorkerState.IDLE: self._worker_allocator.add_idle_worker,
            WorkerState.SETUP_COMPLETED: self._handle_setup_success_on_worker,
            WorkerState.SETUP_FAILED: self._handle_setup_failure_on_worker,
        }

        if new_worker_state not in worker_transition_functions:
            raise BadRequestError('Invalid worker state "{}". Valid states are: {}.'
                                  .format(new_worker_state, ', '.join(worker_transition_functions.keys())))

        do_transition = worker_transition_functions.get(new_worker_state)
        do_transition(worker)

    def update_worker_last_heartbeat_time(self, worker):
        worker.update_last_heartbeat_time()

    def set_shutdown_mode_on_workers(self, worker_ids):
        """
        :type worker_ids: list[int]
        """
        # Find all the workers first so if an invalid worker_id is specified, we 404 before shutting any of them down.
        workers = [self._worker_registry.get_worker(worker_id=worker_id) for worker_id in worker_ids]
        for worker in workers:
            self.handle_worker_state_update(worker, WorkerState.SHUTDOWN)

    def _graceful_shutdown_worker(self, worker):
        """
        Puts worker in shutdown mode so it cannot receive new builds. The worker will be killed when finished with any
        running builds.
        :type worker: Worker
        """
        worker.set_shutdown_mode()
        self._logger.info('Worker on {} was put in shutdown mode. (id: {})', worker.url, worker.id)

    def _disconnect_worker(self, worker):
        """
        Mark a worker dead.

        :type worker: Worker
        """
        # Mark worker dead. We do not remove it from the list of all workers. We also do not remove it from idle_workers;
        # that will happen during worker allocation.
        worker.mark_dead()
        # todo: Fail/resend any currently executing subjobs still executing on this worker.
        self._logger.info('Worker on {} was disconnected. (id: {})', worker.url, worker.id)

    def _handle_setup_success_on_worker(self, worker: Worker):
        """
        Respond to successful build setup on a worker. This starts subjob executions on the worker. This should be called
        once after the specified worker has already run build_setup commands for the specified build.
        """
        build = self.get_build(worker.current_build_id)
        scheduler = self._scheduler_pool.get(build)
        self._thread_pool_executor.submit(scheduler.begin_subjob_executions_on_worker, worker=worker)

    def _handle_setup_failure_on_worker(self, worker):
        """
        Respond to failed build setup on a worker. This should put the worker back into a usable state.

        :type worker: Worker
        """
        build = self.get_build(worker.current_build_id)
        build.setup_failures += 1
        if build.setup_failures >= MAX_SETUP_FAILURES:
            build.cancel()
            build.mark_failed('Setup failed on this build more than {} times. Failing the build.'
                              .format(MAX_SETUP_FAILURES))
        worker.teardown()

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
            BuildStore.add(build)
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
        build = BuildStore.get(int(build_id))
        if build is None:
            raise ItemNotFoundError('Invalid build id.')

        success, response = build.validate_update_params(update_params)
        if not success:
            return success, response
        return build.update_state(update_params), {}

    def handle_result_reported_from_worker(self, worker_url, build_id, subjob_id, payload=None):
        """
        Process the result and dispatch the next subjob
        :type worker_url: str
        :type build_id: int
        :type subjob_id: int
        :type payload: dict
        :rtype: str
        """
        self._logger.info('Results received from {} for subjob. (Build {}, Subjob {})', worker_url, build_id, subjob_id)
        build = BuildStore.get(int(build_id))
        worker = self._worker_registry.get_worker(worker_url=worker_url)
        try:
            build.complete_subjob(subjob_id, payload)
        finally:
            scheduler = self._scheduler_pool.get(build)
            self._thread_pool_executor.submit(scheduler.execute_next_subjob_or_free_executor,
                                              worker=worker)

    def get_build(self, build_id):
        """
        Returns a build by id
        :param build_id: The id for the build whose status we are getting
        :type build_id: int
        :rtype: Build
        """
        build = BuildStore.get(build_id)
        if build is None:
            raise ItemNotFoundError('Invalid build id: {}.'.format(build_id))

        return build

    def get_path_for_build_results_archive(self, build_id: int, is_tar_request: bool=False) -> str:
        """
        Given a build id, get the absolute file path for the archive file containing the build results.

        :param build_id: The build id for which to retrieve the artifacts archive file
        :param is_tar_request: If true, download the tar.gz archive instead of a zip.
        :return: The path to the archived results file
        """
        build = BuildStore.get(build_id)
        if build is None:
            raise ItemNotFoundError('Invalid build id.')

        archive_file = build.artifacts_tar_file if is_tar_request else build.artifacts_zip_file
        if archive_file is None:
            raise ItemNotReadyError('Build artifact file is not yet ready. Try again later.')

        return archive_file
