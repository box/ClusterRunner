from enum import Enum
import os
from queue import Queue, Empty
from threading import Lock

from app.master.build_artifact import BuildArtifact
from app.util.conf.configuration import Configuration
from app.util.counter import Counter
from app.util.exceptions import ItemNotFoundError
import app.util.fs
from app.util.log import get_logger
from app.util.single_use_coin import SingleUseCoin
from app.util.safe_thread import SafeThread


class Build(object):
    """
    A build is a single execution of any configured job. This class:
        - exposes the overall status of the build
        - keeps track of the build's subjobs and their completion state
        - manages slaves that have been assigned to accept this build's subjobs
    """
    _build_id_counter = Counter()  # class-level counter for assigning build ids

    def __init__(self, build_request):
        """
        :type build_request: BuildRequest
        """
        self._logger = get_logger(__name__)
        self._build_id = self._build_id_counter.increment()
        self.build_request = build_request
        self._artifacts_archive_file = None
        self._build_artifact = None
        """ :type : BuildArtifact"""

        self._error_message = None
        self.is_prepared = False
        self._preparation_coin = SingleUseCoin()  # protects against separate threads calling prepare() more than once

        self._project_type = None
        self._build_completion_lock = Lock()  # protects against more than one thread detecting the build's finish
        self._num_executors_allocated = 0
        self._num_executors_in_use = 0
        self._max_executors = float('inf')
        self._build_completion_lock = Lock()

        self._all_subjobs_by_id = {}
        self._unstarted_subjobs = None
        self._finished_subjobs = None
        self._postbuild_tasks_are_finished = False
        self._teardowns_finished = False

    def api_representation(self):
        return {
            'id': self._build_id,
            'status': self._status(),
            'artifacts': self._artifacts_archive_file,  # todo: this should probably be a url, not a file path
            'details': self._detail_message,
            'error_message': self._error_message,
            'num_atoms': self._num_atoms,
            'num_subjobs': len(self._all_subjobs_by_id),
            'failed_atoms': self._failed_atoms(),  # todo: print the file contents instead of paths
            'result': self._result(),
        }

    def prepare(self, subjobs, project_type, job_config):
        """
        :type subjobs: list[Subjob]
        :type project_type: project_type.project_type.ProjectType
        :type job_config: master.job_config.JobConfig
        """
        if not self._preparation_coin.spend():
            raise RuntimeError('prepare() was called more than once on build {}.'.format(self._build_id))

        self._project_type = project_type
        self._unstarted_subjobs = Queue(maxsize=len(subjobs))
        self._finished_subjobs = Queue(maxsize=len(subjobs))

        for subjob in subjobs:
            self._all_subjobs_by_id[subjob.subjob_id()] = subjob
            self._unstarted_subjobs.put(subjob)

        self._max_executors = job_config.max_executors
        self._timing_file_path = project_type.timing_file_path(job_config.name)
        self.is_prepared = True

    def finish(self):
        """
        Called when all slaves are done with this build (and any teardown is complete)
        """
        if self._subjobs_are_finished:
            self._teardowns_finished = True
        else:
            raise RuntimeError('Tried to finish build {} but not all subjobs are complete'.format(self._build_id))

    def build_id(self):
        """
        :rtype: int
        """
        return self._build_id

    def needs_more_slaves(self):
        """
        Determine whether or not this build should have more slaves allocated to it.

        :rtype: bool
        """
        return self._num_executors_allocated < self._max_executors and not self._unstarted_subjobs.empty()

    def allocate_slave(self, slave):
        """
        Allocate a slave to this build. This tells the slave to execute setup commands for this build.

        :type slave: Slave
        """
        slave.setup(self.build_id(), project_type_params=self.build_request.build_parameters())
        self._num_executors_allocated += slave.num_executors

    def all_subjobs(self):
        """
        Returns a list of subjobs for this build
        :rtype: list[Subjob]
        """
        return [subjob for subjob in self._all_subjobs_by_id.values()]

    def subjob(self, subjob_id):
        """
        Returns a single subjob
        :type subjob_id: int
        :rtype: Subjob
        """
        subjob = self._all_subjobs_by_id.get(subjob_id)
        if subjob is None:
            raise ItemNotFoundError('Invalid subjob id.')
        return subjob

    def begin_subjob_executions_on_slave(self, slave):
        """
        Begin subjob executions on a slave. This should be called once after the specified slave has already run
        build_setup commands for this build.

        :type slave: Slave
        """
        for _ in range(slave.num_executors):
            if self._num_executors_in_use >= self._max_executors:
                break
            slave.claim_executor()
            self._num_executors_in_use += 1
            self.execute_next_subjob_on_slave(slave)

    def execute_next_subjob_on_slave(self, slave):
        """
        Grabs an unstarted subjob off the queue and sends it to the specified slave to be executed. If the unstarted
        subjob queue is empty, we mark the slave as idle.

        :type slave: Slave
        """
        try:
            subjob = self._unstarted_subjobs.get(block=False)
            self._logger.debug('Sending subjob {} (build {}) to slave {}.',
                               subjob.subjob_id(), subjob.build_id(), slave.url)
            slave.start_subjob(subjob)

        except Empty:
            num_executors_in_use = slave.free_executor()
            if num_executors_in_use == 0:
                slave.teardown()

    def handle_subjob_payload(self, subjob_id, payload=None):
        if not payload:
            self._logger.warning('No payload for subjob {}.', subjob_id)
            return

        # Assertion: all payloads received from subjobs are uniquely named.
        result_file_path = os.path.join(
            self._build_results_dir(),
            payload['filename'])

        try:
            app.util.fs.write_file(payload['body'], result_file_path)
            app.util.fs.extract_tar(result_file_path, delete=True)
            self._logger.debug('Payload for subjob {} written.', subjob_id)
        except:
            self._logger.warning('Writing payload for subjob {} FAILED.', subjob_id)
            raise

    def _read_subjob_timings_from_results(self):
        """
        Collect timing data from all subjobs
        :rtype: dict [str, float]
        """
        timings = {}
        for _, subjob in self._all_subjobs_by_id.items():
            timings.update(subjob.read_timings())

        return timings

    def mark_subjob_complete(self, subjob_id):
        """
        :type subjob_id: int
        """
        subjob = self._all_subjobs_by_id[int(subjob_id)]
        with self._build_completion_lock:
            self._finished_subjobs.put(subjob, block=False)
            subjobs_are_finished = self._subjobs_are_finished

        # We use a local variable here which was set inside the _build_completion_lock to prevent a race condition
        if subjobs_are_finished:
            self._logger.info("All results received for build {}!", self._build_id)
            SafeThread(target=self._perform_async_postbuild_tasks, name='PostBuild{}'.format(self._build_id)).start()

    def mark_failed(self, failure_reason):
        """
        Mark a build as failed and set a failure reason. The failure reason should be something we can present to the
        end user of ClusterRunner, so try not to include detailed references to internal implementation.

        :type failure_reason: str
        """
        self._logger.error('Build {} failed: {}', self.build_id(), failure_reason)
        self._error_message = failure_reason

    @property
    def artifacts_archive_file(self):
        return self._artifacts_archive_file

    @property
    def _num_subjobs_total(self):
        return len(self._all_subjobs_by_id)

    @property
    def _num_subjobs_finished(self):
        return 0 if not self._finished_subjobs else self._finished_subjobs.qsize()

    @property
    def _num_atoms(self):
        if self._status() not in [BuildStatus.BUILDING, BuildStatus.FINISHED]:
            return None
        return sum([len(subjob.atomic_commands()) for subjob in self._all_subjobs_by_id.values()])

    @property
    def _subjobs_are_finished(self):
        return self.is_prepared and self._finished_subjobs.full()

    @property
    def is_finished(self):
        return self._subjobs_are_finished and self._postbuild_tasks_are_finished and self._teardowns_finished

    @property
    def is_unstarted(self):
        return self.is_prepared and self._num_executors_allocated == 0 and self._unstarted_subjobs.full()

    @property
    def has_error(self):
        return self._error_message is not None

    @property
    def _detail_message(self):
        if self._num_subjobs_total > 0:
            return '{} of {} subjobs are complete ({:.1f}%).'.format(
                self._num_subjobs_finished,
                self._num_subjobs_total,
                100 * self._num_subjobs_finished / self._num_subjobs_total
            )
        return None

    def _status(self):
        """
        :rtype: BuildStatus
        """
        if self.has_error:
            return BuildStatus.ERROR
        elif not self.is_prepared or self.is_unstarted:
            return BuildStatus.QUEUED
        elif self.is_finished:
            return BuildStatus.FINISHED
        else:
            return BuildStatus.BUILDING

    def _failed_atoms(self):
        """
        The commands which failed
        :rtype: list [str] | None
        """
        if self.is_finished:
            # dict.values() returns a view object in python 3, so wrapping values() in a list
            return list(self._build_artifact.get_failed_commands().values())
        return None

    def _result(self):
        """
        :rtype: str | None
        """
        if self.is_finished:
            if len(self._build_artifact.get_failed_commands()) == 0:
                return BuildResult.NO_FAILURES
            return BuildResult.FAILURE
        return None

    def _perform_async_postbuild_tasks(self):
        """
        Once a build is complete, certain tasks can be performed asynchronously.
        """
        # @TODO There is a race condition here where the build is marked finished before the results archive
        # is prepared.  If the user requests the build status before archival finishes, the 'artifacts'
        # value in the post body will be None.  self.is_finished should be conditional on whether archival
        # is finished.
        self._create_build_artifact()
        self._logger.debug('Postbuild tasks completed for build {}', self.build_id())
        self._postbuild_tasks_are_finished = True

    def _create_build_artifact(self):
        self._build_artifact = BuildArtifact(self._build_results_dir())
        self._build_artifact.generate_failures_file()
        self._build_artifact.write_timing_data(self._timing_file_path, self._read_subjob_timings_from_results())
        self._artifacts_archive_file = app.util.fs.compress_directory(self._build_results_dir(), 'results.tar.gz')

    def _build_results_dir(self):
        return os.path.join(
            Configuration['results_directory'],
            str(self.build_id()),
        )


class BuildStatus(str, Enum):
    """
    An enum of possible build statuses. Also inherits from string to allow comparisons with other strings (which is
    useful for client code in parsing API responses).
    """
    QUEUED = 'QUEUED'
    BUILDING = 'BUILDING'
    FINISHED = 'FINISHED'
    ERROR = 'ERROR'


class BuildResult(str, Enum):
    """
    A list of possible results for a completed build.
    """
    NO_FAILURES = 'NO_FAILURES'
    FAILURE = 'FAILURE'
