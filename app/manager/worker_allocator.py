from app.util.log import get_logger
from app.util.ordered_set_queue import OrderedSetQueue
from app.util.safe_thread import SafeThread

from app.manager.worker import WorkerMarkedForShutdownError


class WorkerAllocator(object):
    """
    The WorkerAllocator class is responsible for allocating workers to prepared builds.
    """

    def __init__(self, scheduler_pool):
        """
        :type scheduler_pool: app.manager.build_scheduler_pool.BuildSchedulerPool
        """
        self._logger = get_logger(__name__)
        self._scheduler_pool = scheduler_pool
        self._idle_workers = OrderedSetQueue()
        self._allocation_thread = SafeThread(
            target=self._worker_allocation_loop, name='WorkerAllocationLoop', daemon=True)

    def start(self):
        """
        Start the infinite loop that will pull off prepared builds from a synchronized queue
        and allocate them workers.
        """
        if self._allocation_thread.is_alive():
            raise RuntimeError('Error: worker allocation loop was asked to start when its already running.')
        self._allocation_thread.start()

    def _worker_allocation_loop(self):
        """
        Builds wait in line for more workers. This method executes in the background on another thread and
        watches for idle workers, then gives them out to the waiting builds.
        """
        while True:
            # This is a blocking call that will block until there is a prepared build.
            build_scheduler = self._scheduler_pool.next_prepared_build_scheduler()

            while build_scheduler.needs_more_workers():
                claimed_worker = self._idle_workers.get()

                # Remove dead and shutdown workers from the idle queue
                if claimed_worker.is_shutdown() or not claimed_worker.is_alive(use_cached=False):
                    continue

                # The build may have completed while we were waiting for an idle worker, so check one more time.
                if build_scheduler.needs_more_workers():
                    # Potential race condition here!  If the build completes after the if statement is checked,
                    # a worker will be allocated needlessly (and run worker.setup(), which can be significant work).
                    self._logger.info('Allocating {} to build {}.', claimed_worker, build_scheduler.build_id)
                    build_scheduler.allocate_worker(claimed_worker)
                else:
                    self.add_idle_worker(claimed_worker)

            self._logger.info('Done allocating workers for build {}.', build_scheduler.build_id)

    def add_idle_worker(self, worker):
        """
        Add a worker to the idle queue.

        :type worker: Worker
        """
        try:
            worker.mark_as_idle()
            self._idle_workers.put(worker)
        except WorkerMarkedForShutdownError:
            pass
