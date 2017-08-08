from queue import Empty
from threading import Lock

from app.common.metrics import ErrorType, internal_errors
from app.master.slave import Slave, SlaveError
from app.util import analytics
from app.util.log import get_logger

# pylint: disable=protected-access
# Disable protected-access for whole file; will be fixing this (by
# moving Build's subjob queues into this class) in a separate change.


class BuildScheduler(object):
    """
    This class handles the logic of taking a Build and distributing its subjobs to
    slaves. There is a one-to-one relationship between instances of this class and
    instances of Build.

    The data flow between this class and Build is unidirectional; the build instance
    itself shouldn't know anything about its scheduler or slaves or where subjobs
    are executing. All that goes here.

    This class is instantiated and managed by a BuildSchedulerPool.
    """
    def __init__(self, build, scheduler_pool):
        """
        :type build: app.master.build.Build
        :type scheduler_pool: app.master.build_scheduler_pool.BuildSchedulerPool
        """
        self._logger = get_logger(__name__)
        self._build = build
        self._scheduler_pool = scheduler_pool

        job_config = build.project_type.job_config()
        self._max_executors = job_config.max_executors
        self._max_executors_per_slave = job_config.max_executors_per_slave

        self._slaves_allocated = []
        self._build_started = False
        self._num_executors_allocated = 0
        self._num_executors_in_use = 0
        self._subjob_assignment_lock = Lock()  # prevents subjobs from being skipped

    @property
    def build_id(self):
        """ :rtype: int """
        return self._build.build_id()

    def needs_more_slaves(self):
        """
        Determine whether or not this build should have more slaves allocated to it.

        :rtype: bool
        """
        if self._num_executors_allocated >= self._max_executors:
            return False
        if self._build._unstarted_subjobs.empty():
            return False
        if self._num_executors_allocated >= len(self._build.get_subjobs()):
            return False
        if self._build.is_canceled:
            return False
        return True

    def allocate_slave(self, slave: Slave) -> bool:
        """
        Allocate a slave to this build. This tells the slave to execute setup commands for this build.
        :param slave: The slave to allocate
        :return: Whether slave allocation was successful; this can fail if the slave is unresponsive
        """
        if not self._build_started:
            self._build_started = True
            self._build.mark_started()

        # Increment executors before triggering setup. This helps make sure the build won't take down
        # every slave in the cluster if setup calls fail because of a problem with the build.
        next_executor_index = self._num_executors_allocated
        self._num_executors_allocated += min(slave.num_executors, self._max_executors_per_slave)
        analytics.record_event(analytics.BUILD_SETUP_START, build_id=self._build.build_id(), slave_id=slave.id)
        self._slaves_allocated.append(slave)

        return slave.setup(self._build, executor_start_index=next_executor_index)

    def begin_subjob_executions_on_slave(self, slave):
        """
        Begin subjob executions on a slave. This should be called once after the specified slave has already run
        build_setup commands for this build.

        :type slave: Slave
        """
        analytics.record_event(analytics.BUILD_SETUP_FINISH, build_id=self._build.build_id(), slave_id=slave.id)
        for slave_executor_count in range(slave.num_executors):
            if (self._num_executors_in_use >= self._max_executors
                    or slave_executor_count >= self._max_executors_per_slave):
                break
            slave.claim_executor()
            self._num_executors_in_use += 1
            self.execute_next_subjob_or_free_executor(slave)

    def execute_next_subjob_or_free_executor(self, slave):
        """
        Grabs an unstarted subjob off the queue and sends it to the specified slave to be executed. If the unstarted
        subjob queue is empty, we teardown the slave to free it up for other builds.

        :type slave: Slave
        """
        if self._build.is_canceled:
            self._free_slave_executor(slave)
            return

        # This lock prevents the scenario where a subjob is pulled from the queue but cannot be assigned to this
        # slave because it is shutdown, so we put it back on the queue but in the meantime another slave enters
        # this method, finds the subjob queue empty, and is torn down.  If that was the last 'living' slave, the
        # build would be stuck.
        with self._subjob_assignment_lock:
            try:
                subjob = self._build._unstarted_subjobs.get(block=False)
            except Empty:
                self._free_slave_executor(slave)
                return
            self._logger.debug('Sending {} to {}.', subjob, slave)
            try:
                slave.start_subjob(subjob)
                subjob.mark_in_progress(slave)

            except SlaveError as ex:
                internal_errors.labels(ErrorType.SubjobWriteFailure).inc()  # pylint: disable=no-member
                self._logger.warning('Failed to start {} on {}: {}. Requeuing subjob and freeing slave executor...',
                                     subjob, slave, repr(ex))
                # An executor is currently allocated for this subjob in begin_subjob_executions_on_slave.
                # Since the slave has been marked for shutdown, we need to free the executor.
                self._build._unstarted_subjobs.put(subjob)
                self._free_slave_executor(slave)

    def _free_slave_executor(self, slave):
        num_executors_in_use = slave.free_executor()
        if num_executors_in_use == 0:
            try:
                self._slaves_allocated.remove(slave)
            except ValueError:
                pass  # We have already deallocated this slave, no need to teardown
            else:
                slave.teardown()
                # If all slaves are removed from a build that isn't done, but had already started, then we must
                # make sure that when slave resources are available again, that this build them allocated.
                # https://github.com/box/ClusterRunner/issues/313
                if len(self._slaves_allocated) == 0 and self.needs_more_slaves():
                    self._scheduler_pool.add_build_waiting_for_slaves(self._build)
