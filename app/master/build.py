from collections import OrderedDict
from enum import Enum
from itertools import islice
import os
from queue import Queue, Empty
import shutil
import tempfile
from threading import Lock, Thread
import time
import uuid

from typing import Dict, List

from app.common.build_artifact import BuildArtifact
from app.common.metrics import build_state_duration_seconds, ErrorType, internal_errors, serialized_build_time_seconds
from app.master.build_fsm import BuildFsm, BuildEvent, BuildState
from app.master.build_request import BuildRequest
from app.master.subjob import Subjob
from app.master.subjob_calculator import compute_subjobs_for_build
from app.project_type.project_type import ProjectType
from app.util import util
from app.util.conf.configuration import Configuration
from app.util.counter import Counter
from app.util.exceptions import ItemNotFoundError
import app.util.fs
from app.util.log import get_logger
from app.util.pagination import get_paginated_indices
from app.util.single_use_coin import SingleUseCoin


MAX_SETUP_FAILURES = 5


class Build(object):
    """
    A build is a single execution of any configured job. This class:
        - exposes the overall status of the build
        - keeps track of the build's subjobs and their completion state
        - manages slaves that have been assigned to accept this build's subjobs

    :type _build_id: int
    :type _build_request: BuildRequest
    :type _build_artifact: None | BuildArtifact
    :type _error_message: None | str
    :type _project_type: None | ProjectType
    :type _timing_file_path: None | str
    """
    _build_id_counter = Counter()  # class-level counter for assigning build ids

    def __init__(self, build_request):
        """
        :type build_request: BuildRequest
        """
        self._logger = get_logger(__name__)
        self._build_id = self._build_id_counter.increment()
        self._build_request = build_request
        self._artifacts_tar_file = None  # DEPRECATED - Use zip file instead
        self._artifacts_zip_file = None
        self._build_artifact = None

        self._error_message = None
        self._preparation_coin = SingleUseCoin()  # protects against separate threads calling prepare() more than once

        self._project_type = None
        self._build_completion_lock = Lock()  # protects against more than one thread detecting the build's finish

        self._all_subjobs_by_id = OrderedDict()
        self._unstarted_subjobs = None  # WIP(joey): Move subjob queues to BuildScheduler class.
        self._finished_subjobs = None
        self._failed_atoms = None
        self._postbuild_tasks_are_finished = False  # WIP(joey): Remove and use build state.
        self._timing_file_path = None

        leave_state_callbacks = {build_state: self._on_leave_state
                                 for build_state in BuildState}
        self._state_machine = BuildFsm(
            build_id=self._build_id,
            enter_state_callbacks={
                BuildState.ERROR: self._on_enter_error_state,
                BuildState.CANCELED: self._on_enter_canceled_state,
                BuildState.PREPARING: self._on_enter_preparing_state,
            },
            leave_state_callbacks=leave_state_callbacks
        )

        # Number of times build_setup has failed on this build. If
        # setup_failures increases beyond MAX_SETUP_FAILURES, the build is
        # cancelled
        self.setup_failures = 0

    def api_representation(self):
        failed_atoms_api_representation = None
        if self._get_failed_atoms() is not None:
            failed_atoms_api_representation = [failed_atom.api_representation()
                                               for failed_atom in self._get_failed_atoms()]
        build_state = self._status()
        # todo: PREPARING/PREPARED are new states -- make sure clients can handle them before exposing.
        if build_state in (BuildState.PREPARING, BuildState.PREPARED):
            build_state = BuildState.QUEUED

        return {
            'id': self._build_id,
            'status': build_state,
            'details': self._detail_message,
            'error_message': self._error_message,
            'num_atoms': self._num_atoms,
            'num_subjobs': len(self._all_subjobs_by_id),
            'failed_atoms': failed_atoms_api_representation,
            'result': self._result(),
            'request_params': self.build_request.build_parameters(),
            # Convert self._state_timestamps to OrderedDict to make raw API response more readable. Sort the entries
            # by numerically increasing dict value, with None values sorting highest.
            'state_timestamps': OrderedDict(sorted(
                [(state.lower(), timestamp) for state, timestamp in self._state_machine.transition_timestamps.items()],
                key=lambda item: item[1] or float('inf'))),
        }

    def generate_project_type(self):
        """
        Instantiate the project type for this build, populating the self._project_type instance variable.

        As a side effect, this method also updates the build request's build_parameters dictionary
        with the unique workspace directory path for this build.

        :raises BuildProjectError when failed to instantiate project type
        """
        # Generate a unique project build directory name that will be symlinked to the actual project directory
        # later on when the project gets fetched.
        build_specific_project_directory = self._generate_unique_symlink_path_for_build_repo()

        # Because build_specific_project_directory is entirely internal and generated by ClusterRunner (it is a
        # build-unique generated symlink), we must manually add it to the project_type_params
        project_type_params = self.build_request.build_parameters()
        project_type_params.update({'build_project_directory': build_specific_project_directory})
        self._project_type = util.create_project_type(project_type_params)
        if self._project_type is None:
            raise BuildProjectError('Build failed due to an invalid project type.')

    def prepare(self):
        if not isinstance(self.build_request, BuildRequest):
            raise RuntimeError('Build {} has no associated request object.'.format(self._build_id))

        if not isinstance(self.project_type, ProjectType):
            raise RuntimeError('Build {} has no project set.'.format(self._build_id))

        if not self._preparation_coin.spend():
            raise RuntimeError('prepare() was called more than once on build {}.'.format(self._build_id))

        self._state_machine.trigger(BuildEvent.START_PREPARE)

    def build_id(self):
        """
        :rtype: int
        """
        return self._build_id

    @property
    def build_request(self):
        """
        :rtype: BuildRequest
        """
        return self._build_request

    def get_subjobs(self, offset: int=None, limit: int=None) -> List['Subjob']:
        """
        Returns a list of subjobs for this build
        :param offset: The starting index of the requested build
        :param limit: The number of builds requested
        """
        num_subjobs = len(self._all_subjobs_by_id)
        start, end = get_paginated_indices(offset, limit, num_subjobs)
        requested_subjobs = islice(self._all_subjobs_by_id, start, end)
        return [self._all_subjobs_by_id[key] for key in requested_subjobs]

    def subjob(self, subjob_id: int) -> Subjob:
        """Return the subjob for this build with the specified id."""
        subjob = self._all_subjobs_by_id.get(subjob_id)
        if subjob is None:
            raise ItemNotFoundError('Invalid subjob id.')
        return subjob

    def complete_subjob(self, subjob_id, payload=None):
        """
        Handle the subjob payload and mark the given subjob id for this build as complete.
        :type subjob_id: int
        :type payload: dict
        """
        try:
            self._handle_subjob_payload(subjob_id, payload)
            self._mark_subjob_complete(subjob_id)

        except Exception:
            self._logger.exception('Error while processing subjob {} payload'.format(subjob_id))
            raise

    def _parse_payload_for_atom_exit_code(self, subjob_id):
        subjob = self.subjob(subjob_id)
        for atom_id in range(len(subjob.atoms)):
            artifact_dir = BuildArtifact.atom_artifact_directory(
                self.build_id(),
                subjob.subjob_id(),
                atom_id,
                result_root=Configuration['results_directory']
            )
            atom_exit_code_file_sys_path = os.path.join(artifact_dir, BuildArtifact.EXIT_CODE_FILE)
            with open(atom_exit_code_file_sys_path, 'r') as atom_exit_code_file:
                subjob.atoms[atom_id].exit_code = int(atom_exit_code_file.read())

    def _handle_subjob_payload(self, subjob_id, payload):
        if not payload:
            self._logger.warning('No payload for subjob {} of build {}.', subjob_id, self._build_id)
            return

        # Assertion: all payloads received from subjobs are uniquely named.
        result_file_path = os.path.join(self._build_results_dir(), payload['filename'])

        try:
            app.util.fs.write_file(payload['body'], result_file_path)
            app.util.fs.extract_tar(result_file_path, delete=False)
            self._parse_payload_for_atom_exit_code(subjob_id)
        except:
            internal_errors.labels(ErrorType.SubjobWriteFailure).inc()  # pylint: disable=no-member
            self._logger.warning('Writing payload for subjob {} of build {} FAILED.', subjob_id, self._build_id)
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

    def _mark_subjob_complete(self, subjob_id):
        """
        :type subjob_id: int
        """
        subjob = self.subjob(subjob_id)
        subjob.mark_completed()
        with self._build_completion_lock:
            self._finished_subjobs.put(subjob, block=False)
            should_trigger_postbuild_tasks = self._all_subjobs_are_finished() and not self.is_stopped

        # We use a local variable here which was set inside the _build_completion_lock to prevent a race condition
        if should_trigger_postbuild_tasks:
            self._logger.info("All results received for build {}!", self._build_id)
            self.finish()

    def mark_started(self):
        """
        Mark the build as started.
        """
        self._state_machine.trigger(BuildEvent.START_BUILDING)

    def finish(self):
        """
        Perform postbuild task and mark this build as finished.
        """
        Thread(
            target=self._perform_async_postbuild_tasks,
            name='PostBuild{}'.format(self._build_id),
        ).start()

    def mark_failed(self, failure_reason):
        """
        Mark a build as failed and set a failure reason. The failure reason should be something we can present to the
        end user of ClusterRunner, so try not to include detailed references to internal implementation.
        :type failure_reason: str
        """
        self._state_machine.trigger(BuildEvent.FAIL, error_msg=failure_reason)

    def _on_enter_error_state(self, event):
        """
        Store an error message for the build and log the failure. This method is triggered by
        a state machine transition to the ERROR state.
        :param event: The Fysom event object
        """
        # WIP(joey): Should this be a reenter_state callback also? Should it check for previous error message?
        default_error_msg = 'An unspecified error occurred.'
        self._error_message = getattr(event, 'error_msg', default_error_msg)
        self._logger.warning('Build {} failed: {}', self.build_id(), self._error_message)

    def _on_enter_preparing_state(self, event):
        """
        Prepare the build by atomization and subjobs creation.
        This method is triggered by a state machine transition to the PREPARING state.
        :param event: The Fysom event object
        :type event: BuildEvent
        """
        self._logger.info('Fetching project for build {}.', self._build_id)
        self.project_type.fetch_project()
        self._logger.info('Successfully fetched project for build {}.', self._build_id)

        job_config = self.project_type.job_config()
        if job_config is None:
            raise RuntimeError('Build failed while trying to parse clusterrunner.yaml.')

        subjobs = compute_subjobs_for_build(self._build_id, job_config, self.project_type)

        self._unstarted_subjobs = Queue(maxsize=len(subjobs))  # WIP(joey): Move this into BuildScheduler?
        self._finished_subjobs = Queue(maxsize=len(subjobs))  # WIP(joey): Remove this and just record finished count.

        for subjob in subjobs:
            self._all_subjobs_by_id[subjob.subjob_id()] = subjob
            self._unstarted_subjobs.put(subjob)

        self._timing_file_path = self._project_type.timing_file_path(job_config.name)
        app.util.fs.create_dir(self._build_results_dir())
        self._state_machine.trigger(BuildEvent.FINISH_PREPARE)

    def _on_leave_state(self, event):
        start_time = self._state_machine.transition_timestamps.get(event.src)
        if start_time is not None:
            elapsed = time.time() - start_time
            build_state_duration_seconds.labels(event.src.value).observe(elapsed)  # pylint: disable=no-member
        else:
            self._logger.warn('Build {} transitioned from state {} to state {} but never marked started timestamp for {}',
                              self._build_id, event.src, event.dst, event.src)

    def cancel(self):
        """
        Cancel a running build.
        """
        self._state_machine.trigger(BuildEvent.CANCEL)

    def _on_enter_canceled_state(self, event):
        """
        :param event: The Fysom event object
        :type event: BuildEvent
        """
        self._logger.notice('Canceling build {}.', self._build_id)
        # Set the kill_event to kill the subprocesses for the build
        self.project_type.kill_subprocesses()

        # Deplete the unstarted subjob queue.
        # WIP(joey): Just remove this completely and adjust behavior of other methods based on self._is_canceled().
        # TODO: Handle situation where cancel() is called while subjobs are being added to _unstarted_subjobs
        while self._unstarted_subjobs is not None and not self._unstarted_subjobs.empty():
            try:
                # A subjob may be asynchronously pulled from this queue, so we need to avoid blocking when empty.
                self._unstarted_subjobs.get(block=False)
            except Empty:
                break

    def validate_update_params(self, update_params):
        """
        Determine if a dict of update params are valid, and generate an error if not
        :param update_params: Params passed into a PUT for this build
        :type update_params: dict [str, str]
        :return: Whether the params are valid and a response containing an error message if not
        :rtype: tuple [bool, dict [str, str]]
        """
        keys_and_values_allowed = {'status': ['canceled']}
        message = None
        for key, value in update_params.items():
            if key not in keys_and_values_allowed.keys():
                message = 'Key ({}) is not in list of allowed keys ({})'.\
                    format(key, ",".join(keys_and_values_allowed.keys()))
            elif value not in keys_and_values_allowed[key]:
                message = 'Value ({}) is not in list of allowed values ({}) for {}'.\
                    format(value, keys_and_values_allowed[key], key)

        if message is not None:
            return False, {'error': message}
        return True, {}

    def update_state(self, update_params):
        """
        Make updates to the state of this build given a set of update params
        :param update_params: The keys and values to update on this build
        :type update_params: dict [str, str]
        """
        success = False
        for key, value in update_params.items():
            if key == 'status':
                if value == 'canceled':
                    self.cancel()
                    success = True
        return success

    @property
    def project_type(self):
        """
        :rtype: ProjectType
        """
        return self._project_type

    @property
    def artifacts_zip_file(self):
        """Return the local path to the artifacts zip archive."""
        return self._artifacts_zip_file

    @property
    def artifacts_tar_file(self):
        """
        DEPRECATED: We are transitioning to zip files from tar.gz files for artifacts.
        Return the local path to the artifacts tar.gz archive.
        """
        self._logger.warning('The tar format for build artifact files is deprecated. File: {}',
                             self._artifacts_tar_file)
        return self._artifacts_tar_file

    # WIP(joey): Change some of these private @properties to methods.
    @property
    def _num_subjobs_total(self):
        return len(self._all_subjobs_by_id)

    @property
    def _num_subjobs_finished(self):
        return 0 if not self._finished_subjobs else self._finished_subjobs.qsize()

    @property
    def _num_atoms(self):
        # todo: blacklist states instead of whitelist, or just check _all_subjobs_by_id directly
        if self._status() not in [BuildState.BUILDING, BuildState.FINISHED]:
            return None
        return sum([len(subjob.atomic_commands()) for subjob in self._all_subjobs_by_id.values()])

    def _all_subjobs_are_finished(self):
        return self._finished_subjobs and self._finished_subjobs.full()

    @property
    def is_finished(self):
        # WIP(joey): Calling logic should check _is_canceled if it needs to instead of including the check here.
        return self.is_canceled or self._postbuild_tasks_are_finished

    @property
    def _detail_message(self):
        if self._num_subjobs_total > 0:
            return '{} of {} subjobs are complete ({:.1f}%).'.format(
                self._num_subjobs_finished,
                self._num_subjobs_total,
                100 * self._num_subjobs_finished / self._num_subjobs_total
            )
        return None

    def _status(self):  # WIP(joey): Rename to _state.
        """
        :rtype: BuildState
        """
        return self._state_machine.state

    @property
    def has_error(self):
        return self._status() is BuildState.ERROR

    @property
    def is_canceled(self):
        return self._status() is BuildState.CANCELED

    @property
    def is_stopped(self):
        return self._status() in (BuildState.ERROR, BuildState.CANCELED)

    def _get_failed_atoms(self):
        """
        The atoms that failed. Returns None if the build hasn't completed yet. Returns empty set if
        build has completed and no atoms have failed.
        :rtype: list[Atom] | None
        """
        if self._failed_atoms is None and self.is_finished:
            if self.is_canceled:
                return []

            self._failed_atoms = []
            for subjob_id, atom_id in self._build_artifact.get_failed_subjob_and_atom_ids():
                subjob = self.subjob(subjob_id)
                atom = subjob.atoms[atom_id]
                self._failed_atoms.append(atom)

        return self._failed_atoms

    def _result(self):
        """
        Can return three states:
            None:
            FAILURE:
            NO_FAILURES:
        :rtype: BuildResult | None
        """
        if self.is_canceled:
            return BuildResult.FAILURE

        if self.is_finished:
            if len(self._build_artifact.get_failed_subjob_and_atom_ids()) == 0:
                return BuildResult.NO_FAILURES
            return BuildResult.FAILURE
        return None

    def _perform_async_postbuild_tasks(self):
        """
        Once a build is complete, execute certain tasks like archiving the artifacts and writing timing
        data. This method also transitions the FSM to finished after the postbuild tasks are complete.
        """
        try:
            timing_data = self._read_subjob_timings_from_results()
            self._create_build_artifact(timing_data)
            serialized_build_time_seconds.observe(sum(timing_data.values()))
            self._delete_temporary_build_artifact_files()
            self._postbuild_tasks_are_finished = True
            self._state_machine.trigger(BuildEvent.POSTBUILD_TASKS_COMPLETE)

        except Exception as ex:  # pylint: disable=broad-except
            internal_errors.labels(ErrorType.PostBuildFailure).inc()  # pylint: disable=no-member
            self._logger.exception('Postbuild tasks failed for build {}.'.format(self._build_id))
            self.mark_failed('Postbuild tasks failed due to an internal error: "{}"'.format(ex))

    def _create_build_artifact(self, timing_data: Dict[str, float]):  # pylint: disable=unsubscriptable-object
        self._build_artifact = BuildArtifact(self._build_results_dir())
        self._build_artifact.generate_failures_file()
        self._build_artifact.write_timing_data(self._timing_file_path, timing_data)
        self._artifacts_tar_file = app.util.fs.tar_directory(self._build_results_dir(),
                                                             BuildArtifact.ARTIFACT_TARFILE_NAME)
        temp_tar_path = None
        try:
            # Temporarily move aside tar file so we can create a zip file, then move it back.
            # This juggling can be removed once we're no longer creating tar artifacts.
            temp_tar_path = shutil.move(self._artifacts_tar_file, tempfile.mktemp())
            self._artifacts_zip_file = app.util.fs.zip_directory(self._build_results_dir(),
                                                                 BuildArtifact.ARTIFACT_ZIPFILE_NAME)
        except Exception:  # pylint: disable=broad-except
            internal_errors.labels(ErrorType.ZipFileCreationFailure).inc()  # pylint: disable=no-member

            # Due to issue #339 we are ignoring exceptions in the zip file creation for now.
            self._logger.exception('Zipping of artifacts failed. This error will be ignored.')
        finally:
            if temp_tar_path:
                shutil.move(temp_tar_path, self._artifacts_tar_file)

    def _delete_temporary_build_artifact_files(self):
        """
        Delete the temporary build result files that are no longer needed, due to the creation of the
        build artifact tarball.

        ONLY call this method after _create_build_artifact() has completed. Otherwise we have lost the build results.
        """
        build_result_dir = self._build_results_dir()
        start_time = time.time()
        for path in os.listdir(build_result_dir):
            # The build result archive is also stored in this same directory, so we must not delete it.
            if path in (BuildArtifact.ARTIFACT_TARFILE_NAME, BuildArtifact.ARTIFACT_ZIPFILE_NAME):
                continue
            full_path = os.path.join(build_result_dir, path)
            # Do NOT use app.util.fs.async_delete() here. That call will generate a temp directory for every
            # atom, which can be in the thousands per build, and can lead to running up against the ulimit -Hn.
            if os.path.isdir:
                shutil.rmtree(full_path, ignore_errors=True)
            else:
                os.remove(full_path)
        end_time = time.time() - start_time
        self._logger.info('Completed deleting artifact files for {}, took {:.1f} seconds.', self._build_id, end_time)

    def _build_results_dir(self):
        return BuildArtifact.build_artifact_directory(self.build_id(), result_root=Configuration['results_directory'])

    def _generate_unique_symlink_path_for_build_repo(self):
        """
        Generate a unique symlink path for a build-specific repo. This method does NOT generate the symlink itself.
        :rtype: str
        """
        return os.path.join(Configuration['build_symlink_directory'], str(uuid.uuid4()))


class BuildStatus(str, Enum):  # WIP(joey): Remove this class.
    """
    An enum of possible build statuses. Also inherits from string to allow comparisons with other strings (which is
    useful for client code in parsing API responses).
    """
    QUEUED = 'QUEUED'
    PREPARED = 'PREPARED'
    BUILDING = 'BUILDING'
    FINISHED = 'FINISHED'
    ERROR = 'ERROR'
    CANCELED = 'CANCELED'


class BuildResult(str, Enum):
    """
    A list of possible results for a completed build.
    """
    NO_FAILURES = 'NO_FAILURES'
    FAILURE = 'FAILURE'


class BuildProjectError(Exception):
    """
    The build project could not be created or fetched
    """
