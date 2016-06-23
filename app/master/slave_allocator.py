from app.util.log import get_logger
from app.util.ordered_set_queue import OrderedSetQueue
from app.util.safe_thread import SafeThread

from app.master.slave import SlaveMarkedForShutdownError


class SlaveAllocator(object):
    """
    The SlaveAllocator class is responsible for allocating slaves to prepared builds.
    """

    def __init__(self, scheduler_pool):
        """
        :type scheduler_pool: app.master.build_scheduler_pool.BuildSchedulerPool
        """
        self._logger = get_logger(__name__)
        self._scheduler_pool = scheduler_pool
        self._idle_slaves = OrderedSetQueue()
        self._allocation_thread = SafeThread(
            target=self._slave_allocation_loop, name='SlaveAllocationLoop', daemon=True)

    def start(self):
        """
        Start the infinite loop that will pull off prepared builds from a synchronized queue
        and allocate them slaves.
        """
        if self._allocation_thread.is_alive():
            raise RuntimeError('Error: slave allocation loop was asked to start when its already running.')
        self._allocation_thread.start()

    def _slave_allocation_loop(self):
        """
        Builds wait in line for more slaves. This method executes in the background on another thread and
        watches for idle slaves, then gives them out to the waiting builds.
        """
        while True:
            # This is a blocking call that will block until there is a prepared build.
            build_scheduler = self._scheduler_pool.next_prepared_build_scheduler()

            while build_scheduler.needs_more_slaves():
                claimed_slave = self._idle_slaves.get()

                # Remove dead and shutdown slaves from the idle queue
                if claimed_slave.is_shutdown() or not claimed_slave.is_alive(use_cached=False):
                    continue

                # The build may have completed while we were waiting for an idle slave, so check one more time.
                if build_scheduler.needs_more_slaves():
                    # Potential race condition here!  If the build completes after the if statement is checked,
                    # a slave will be allocated needlessly (and run slave.setup(), which can be significant work).
                    self._logger.info('Allocating {} to build {}.', claimed_slave, build_scheduler.build_id)
                    build_scheduler.allocate_slave(claimed_slave)
                else:
                    self.add_idle_slave(claimed_slave)

            self._logger.info('Done allocating slaves for build {}.', build_scheduler.build_id)

    def add_idle_slave(self, slave):
        """
        Add a slave to the idle queue.

        :type slave: Slave
        """
        try:
            slave.mark_as_idle()
            self._idle_slaves.put(slave)
        except SlaveMarkedForShutdownError:
            pass
