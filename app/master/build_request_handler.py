from queue import Queue
from threading import Lock

from app.util import analytics
from app.util.log import get_logger
from app.util.safe_thread import SafeThread


class BuildRequestHandler(object):
    """
    The BuildRequestHandler class is responsible for preparing a non-prepared build.

    Implementation notes:

    This class manages two critical Queues in ClusterRunner: request_queue and builds_waiting_for_slaves.

    The request_queue is the queue of non-prepared Build instances that the BuildRequestHandler has
    yet to prepare. This queue is populated by the ClusterMaster instance.

    The builds_waiting_for_slaves queue is the queue of prepared Build instances that the
    BuildRequestHandler has completed build preparation for, and is waiting for the SlaveAllocator (a separate
    entity) to pull Builds from.

    All of the input of builds come through self.handle_build_request() calls, and all of the output
    of builds go through self._scheduler_pool.next_prepared_build_scheduler() calls.
    """
    def __init__(self, scheduler_pool):
        """
        :type scheduler_pool: app.master.build_scheduler_pool.BuildSchedulerPool
        """
        self._logger = get_logger(__name__)
        self._scheduler_pool = scheduler_pool
        self._request_queue = Queue()
        self._request_queue_worker_thread = SafeThread(
            target=self._build_preparation_loop, name='RequestHandlerLoop', daemon=True)
        self._project_preparation_locks = {}

    def start(self):
        """
        Start the infinite loop that will accept unprepared builds and put them through build preparation.
        """
        if self._request_queue_worker_thread.is_alive():
            raise RuntimeError('Error: build request handler loop was asked to start when its already running.')
        self._request_queue_worker_thread.start()

    def handle_build_request(self, build):
        """
        :param build: the requested build
        :type build: Build
        """
        self._request_queue.put(build)
        analytics.record_event(analytics.BUILD_REQUEST_QUEUED, build_id=build.build_id(),
                               log_msg='Queued request for build {build_id}.')

    def _build_preparation_loop(self):
        """
        Grabs a build off the request_queue (populated by self.handle_build_request()), prepares it,
        and puts that build onto the self.builds_waiting_for_slaves queue.
        """
        while True:
            build = self._request_queue.get()
            project_id = build.project_type.project_id()

            if project_id not in self._project_preparation_locks:
                self._logger.info('Creating project lock [{}] for build {}', project_id, str(build.build_id()))
                self._project_preparation_locks[project_id] = Lock()

            project_lock = self._project_preparation_locks[project_id]
            SafeThread(
                target=self._prepare_build_async,
                name='Bld{}-PreparationThread'.format(build.build_id()),
                args=(build, project_lock)
            ).start()

    def _prepare_build_async(self, build, project_lock):
        """
        :type build: app.master.build.Build
        :type project_lock: Lock
        """
        self._logger.info('Build {} is waiting for the project lock', build.build_id())

        with project_lock:
            self._logger.info('Build {} has acquired project lock', build.build_id())
            analytics.record_event(analytics.BUILD_PREPARE_START, build_id=build.build_id(),
                                   log_msg='Build preparation loop is handling request for build {build_id}.')
            try:
                build.prepare()
                if not build.is_stopped:
                    analytics.record_event(analytics.BUILD_PREPARE_FINISH, build_id=build.build_id(), is_success=True,
                                           log_msg='Build {build_id} successfully prepared.')
                    # If the atomizer found no work to do, perform build cleanup and skip the slave allocation.
                    if len(build.get_subjobs()) == 0:
                        self._logger.info('Build {} has no work to perform and is exiting.', build.build_id())
                        build.finish()
                    # If there is work to be done, this build must queue to be allocated slaves.
                    else:
                        self._logger.info('Build {} is waiting for slaves.', build.build_id())
                        self._scheduler_pool.add_build_waiting_for_slaves(build)

            except Exception as ex:  # pylint: disable=broad-except
                if not build.is_canceled:
                    build.mark_failed(str(ex))  # WIP(joey): Build should do this internally.
                    self._logger.exception('Could not handle build request for build {}.'.format(build.build_id()))
                analytics.record_event(analytics.BUILD_PREPARE_FINISH, build_id=build.build_id(), is_success=False)
