from collections import OrderedDict
import json
from queue import Queue
from typing import List, Optional
from sqlalchemy import func

from app.database.connection import Connection
from app.database.database_setup import DatabaseSetup
from app.database.schema import (
    BuildStateSchema,
    BuildMetaSchema,
    BuildArtifactSchema,
    FailedArtifactDirectoriesSchema,
    FailedSubjobAtomPairsSchema,
    BuildRequestSchema,
    BuildFsmSchema,
    SubjobsSchema,
    AtomsSchema
)
from app.common.build_artifact import BuildArtifact
from app.master.atom import Atom
from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.build_fsm import BuildState
from app.master.subjob import Subjob
from app.util.exceptions import ItemNotFoundError
from app.util.log import get_logger
from app.util.conf.configuration import Configuration


# pylint: disable=protected-access
class BuildStore:
    """
    Build storage service that stores and handles all builds.
    """

    def __init__(self):
        self._logger = get_logger(__name__)
        self._cached_builds_by_id = OrderedDict()
        self._session = Connection.get(Configuration['database_url'])
        # TODO: Resetting the database empties all data currently stored.
        #       Preparing the database attempts to build all the tables if they aren't already created.
        #       These should be called somewhere else if ever, here right now for testing.
        DatabaseSetup.prepare()
        # DatabaseSetup.reset()

    def get(self, build_id: int, allow_incompleted_builds=False) -> Optional[Build]:
        """
        Returns a build by id.
        :param build_id: The id for the build whose status we are getting
        """
        build = self._cached_builds_by_id.get(build_id)
        if build is None:
            self._logger.info('Requested build (id: {}) was not found in cache, checking database.'.format(build_id))
            build = self._reconstruct_build(build_id, allow_incompleted_builds=allow_incompleted_builds)
            if build is not None:
                self._cached_builds_by_id[build_id] = build
                self._logger.notice('Build (id: {}) was added to cache.'.format(build_id))

        return build

    def get_range(self, start: int, end: int, allow_incompleted_builds=False) -> List[Build]:
        """
        Returns a list of all builds.
        :param start: The starting index of the requested build.
        :param end: 1 + the index of the last requested element, although if this is greater than the total number
                    of builds available the length of the returned list may be smaller than (end - start).
        """
        # Add 1 to start & end because we're create build_id's, not indices
        builds = []
        for build_id in range(start + 1, end + 1):
            try:
                builds.append(self.get(build_id, allow_incompleted_builds=allow_incompleted_builds))
            except IncompleteBuild:
                builds.append(None)
        return builds

    def add(self, build: Build):
        """
        Add new build to collection.
        :param build: The build to add to the store.
        """
        build_id = self._store_build(build)
        build._build_id = build_id
        self._cached_builds_by_id[build_id] = build

    def save(self, build: Build):
        """
        Save current state of given build.
        We assume that this build already exists in the database. You should always call `add` before
        trying to ever call a `save`. This should already be done for you in cluster_master.
        We also assume this build is already in the cache in its current state.
        :param build: The build to save to database.
        """
        self._logger.notice('Saving build (id: {}) in database.'.format(build.build_id()))
        self._update_build(build)

    def clean_up(self):
        """
        Save current state of all cached builds.
        """
        for build_id in self._cached_builds_by_id:
            build = self._cached_builds_by_id[build_id]
            self._update_build(build)
        self._session.commit()

    def count_all_builds(self) -> int:
        """
        Return the total amount of builds stored in the database.
        """
        return self._session.query(func.count('*')).select_from(BuildStateSchema).scalar()

    def count_cached_builds(self) -> int:
        """
        Return the amount of builds stored in the cache.
        """
        return len(self._cached_builds_by_id)

    def _store_build(self, build: Build) -> int:
        """
        Serialize a Build object and commit all of the parts to the database, and then
        return the build_id that was assigned after committing.
        :param build: The build to store into the database.
        """
        # Build Status
        build_schema = BuildStateSchema(
            completed=build._status() == BuildState.FINISHED
        )
        self._session.add(build_schema)

        # Commit this first to get the build_id created by the database
        # We use this build_id to store the other parts of a Build object
        self._session.commit()
        build_id = build_schema.build_id

        # Build Meta
        build_meta = BuildMetaSchema(
            build_id=build_id,
            artifacts_tar_file=build._artifacts_tar_file,
            artifacts_zip_file=build._artifacts_zip_file,
            error_message=build._error_message,
            postbuild_tasks_are_finished=bool(build._postbuild_tasks_are_finished),
            timing_file_path=build._timing_file_path,
            setup_failures=build.setup_failures
        )
        self._session.add(build_meta)

        # BuildArtifacts
        build_artifact_dir = None
        if build._build_artifact is not None:
            build_artifact_dir = build._build_artifact.build_artifact_dir
        build_artifacts = BuildArtifactSchema(
            build_id=build_id,
            build_artifact_dir=build_artifact_dir
        )
        self._session.add(build_artifacts)

        # FailedArtifactDirectories
        if build._build_artifact is not None:
            for directory in build._build_artifact._get_failed_artifact_directories():
                failed_artifact_directory = FailedArtifactDirectoriesSchema(
                    build_id=build_id,
                    failed_artifact_directory=directory
                )
                self._session.add(failed_artifact_directory)

        # FailedSubjobAtomPairs
        if build._build_artifact is not None:
            for subjob_id, atom_id in build._build_artifact.get_failed_subjob_and_atom_ids():
                failed_subjob_and_atom_ids = FailedSubjobAtomPairsSchema(
                    build_id=build_id,
                    subjob_id=subjob_id,
                    atom_id=atom_id
                )
                self._session.add(failed_subjob_and_atom_ids)

        # BuildRequest
        build_params = build._build_request._build_parameters
        build_request = BuildRequestSchema(
            build_id=build_id,
            build_parameters=json.dumps(build._build_request.build_parameters())
        )
        self._session.add(build_request)

        # BuildFsm
        fsm_timestamps = {state.lower(): timestamp for state, timestamp in build._state_machine.transition_timestamps.items()}
        build_fsm = BuildFsmSchema(
            build_id=build_id,
            state=build._status(),
            queued=fsm_timestamps['queued'],
            finished=fsm_timestamps['finished'],
            prepared=fsm_timestamps['prepared'],
            preparing=fsm_timestamps['preparing'],
            error=fsm_timestamps['error'],
            canceled=fsm_timestamps['canceled'],
            building=fsm_timestamps['building']
        )
        self._session.add(build_fsm)

        # Subjobs
        subjobs = build._all_subjobs_by_id
        for subjob_id in subjobs:
            subjob = build._all_subjobs_by_id[subjob_id]
            subjob_schema = SubjobsSchema(
                subjob_id=subjob_id,
                build_id=build_id,
                completed=subjob.completed
            )
            self._session.add(subjob_schema)

            # Atoms
            for atom in subjob._atoms:
                atom_schema = AtomsSchema(
                    atom_id=atom.id,
                    build_id=build_id,
                    subjob_id=subjob_id,
                    command_string=atom.command_string,
                    expected_time=atom.expected_time,
                    actual_time=atom.actual_time,
                    exit_code=atom.exit_code,
                    state=atom.state,
                )
                self._session.add(atom_schema)

        # Save changes
        self._session.commit()
        return build_id

    def _update_build(self, build: Build) -> int:
        """
        Serialize a Build object and update all of the parts to the database.
        NOTE: These changes are not committed here. If you want these changes to persist, \
              make sure to commit the session afterwards. \
              We do selectively call commit a few times here but only after we delete rows.
        :param build_id: The build_id of the build to update in the database.
        """
        build_id = build.build_id()
        (
            q_build_schema,
            q_build_state,
            q_build_meta,
            q_build_artifact,
            _,
            _,
            q_build_request,
            q_build_fsm,
            _,
            _) = self._get_query_build_object(build_id)

        # If this wasn't found, it's safe to assume that the build doesn't exist within the database
        if q_build_schema is None:
            raise ItemNotFoundError('Unable to find build (id: {}) in database.'.format(build_id))

        q_build_schema.completed = build._status() == BuildState.FINISHED

        q_build_meta.artifacts_tar_file = build._artifacts_tar_file
        q_build_meta.artifacts_zip_file = build._artifacts_zip_file
        q_build_meta.error_message = build._error_message
        q_build_meta.postbuild_tasks_are_finished = build._postbuild_tasks_are_finished
        q_build_meta.setup_failures = build.setup_failures
        q_build_meta.timing_file_path = build._timing_file_path

        # Query for BuildArtifact associated with this `build_id`
        build_artifact_dir = None
        if build._build_artifact is not None:
            build_artifact_dir = build._build_artifact.build_artifact_dir

        q_build_artifact.build_artifact_dir = build_artifact_dir

        # Query for the FailedArtifactDirectories associated with this `build_id`
        if build._build_artifact is not None:
            # Clear all old directories associated with this `build_id`
            self._session.query(FailedArtifactDirectoriesSchema) \
                .filter(FailedArtifactDirectoriesSchema.build_id == build_id) \
                .delete()

            # Commit changes so we don't delete the newly added rows later
            self._session.commit()

            # Add all the updated versions of the directories
            for directory in build._build_artifact._get_failed_artifact_directories():
                failed_artifact_directory = FailedArtifactDirectoriesSchema(
                    build_id=build_id,
                    failed_artifact_directory=directory
                )
                self._session.add(failed_artifact_directory)

        # Query for the FailedSubjobAtomPairs associated with this `build_id`
        if build._build_artifact is not None:
            # Clear all old data associated with this build_id
            self._session.query(FailedSubjobAtomPairsSchema) \
                .filter(FailedSubjobAtomPairsSchema.build_id == build_id) \
                .delete()

            # Commit changes so we don't delete the newly added rows later
            self._session.commit()

            # Add all the updated versions of the data
            for subjob_id, atom_id in build._build_artifact.get_failed_subjob_and_atom_ids():
                failed_subjob_and_atom_ids = FailedSubjobAtomPairsSchema(
                    build_id=build_id,
                    subjob_id=subjob_id,
                    atom_id=atom_id
                )
                self._session.add(failed_subjob_and_atom_ids)

        q_build_request.build_parameters = json.dumps(build._build_request.build_parameters())

        fsm_timestamps = {state.lower(): timestamp for state, timestamp in build._state_machine.transition_timestamps.items()}
        q_build_fsm.state = build._status()
        q_build_fsm.queued = fsm_timestamps['queued']
        q_build_fsm.finished = fsm_timestamps['finished']
        q_build_fsm.prepared = fsm_timestamps['prepared']
        q_build_fsm.preparing = fsm_timestamps['preparing']
        q_build_fsm.error = fsm_timestamps['error']
        q_build_fsm.canceled = fsm_timestamps['canceled']
        q_build_fsm.building = fsm_timestamps['building']

        # Subjobs
        # Clear all old Subjobs and Atoms associated with this `build_id`
        self._session.query(SubjobsSchema) \
            .filter(SubjobsSchema.build_id == build_id) \
            .delete()
        self._session.query(AtomsSchema) \
            .filter(AtomsSchema.build_id == build_id) \
            .delete()

        # Commit changes so we don't delete the newly added rows later
        self._session.commit()

        # Add all the updated versions of Subjobs and Atoms
        subjobs = build._all_subjobs_by_id
        for subjob_id in subjobs:
            subjob = build._all_subjobs_by_id[subjob_id]
            subjob_schema = SubjobsSchema(
                subjob_id=subjob_id,
                build_id=build_id,
                completed=subjob.completed
            )
            self._session.add(subjob_schema)

            # Atoms
            for atom in subjob._atoms:
                atom_schema = AtomsSchema(
                    atom_id=atom.id,
                    build_id=build_id,
                    subjob_id=subjob_id,
                    command_string=atom.command_string,
                    expected_time=atom.expected_time,
                    actual_time=atom.actual_time,
                    exit_code=atom.exit_code,
                    state=atom.state
                )
                self._session.add(atom_schema)

    def _reconstruct_build(self, build_id, allow_incompleted_builds=False) -> Build:
        """
        Given a build_id, fetch all the stored information from the database to reconstruct
        a Build object to represent that build.
        :param build_id: The id of the build to recreate.
        """
        (
            q_build_schema,
            q_build_state,
            q_build_meta,
            q_build_artifact,
            q_failed_artifact_directories,
            q_failed_subjob_atom_pairs,
            q_build_request,
            q_build_fsm,
            q_build_subjobs,
            q_build_atoms
        ) = self._get_query_build_object(build_id)

        # If a query returns None, then we know the build wasn't found in the database
        if not q_build_schema:
            return None

        # Build wasn't completed when we stored it
        if not allow_incompleted_builds and not bool(int(q_build_schema.completed)):
            raise IncompleteBuild('Cannot load build (id: {}) because it was never completed.'.format(build_id))

        build_parameters = json.loads(q_build_request.build_parameters)

        # Genereate a BuildRequest object with our query response
        build_request = BuildRequest(build_parameters)

        # Create initial Build object, we will be altering the state of this as we get more data
        build = Build(build_request)
        build._build_id = build_id

        # Manually generate ProjectType object for build and create a `job_config` since this is usually done in `prepare()`
        build.generate_project_type()
        job_config = build.project_type.job_config()

        # Manually update build data
        build._artifacts_tar_file = q_build_meta.artifacts_tar_file
        build._artifacts_zip_file = q_build_meta.artifacts_zip_file
        build._error_message = q_build_meta.error_message
        build._postbuild_tasks_are_finished = bool(int(q_build_meta.postbuild_tasks_are_finished))
        build.setup_failures = q_build_meta.setup_failures
        build._timing_file_path = q_build_meta.timing_file_path

        # Manually set the state machine timestamps
        build._state_machine._transition_timestamps = {
            BuildState.QUEUED: q_build_fsm.queued,
            BuildState.FINISHED: q_build_fsm.finished,
            BuildState.PREPARED: q_build_fsm.prepared,
            BuildState.PREPARING: q_build_fsm.preparing,
            BuildState.ERROR: q_build_fsm.error,
            BuildState.CANCELED: q_build_fsm.canceled,
            BuildState.BUILDING: q_build_fsm.building
        }
        build._state_machine._fsm.current = BuildState[q_build_fsm.state]

        # Create the `build_artifact`, we will be altering its attributes as we get more data
        build_artifact = BuildArtifact(q_build_artifact.build_artifact_dir)

        directories = []
        for directory in q_failed_artifact_directories:
            directories.append(directory.failed_artifact_directory)
        build_artifact._failed_artifact_directories = directories

        pairs = []
        for pair in q_failed_subjob_atom_pairs:
            pairs.append((pair.subjob_id, pair.atom_id))
        build_artifact._q_failed_subjob_atom_pairs = pairs

        # The `build_artifact` is prepared, so manually assign it to build
        build._build_artifact = build_artifact

        atoms_by_subjob_id = {}
        for atom in q_build_atoms:
            atoms_by_subjob_id.setdefault(atom.subjob_id, [])
            atoms_by_subjob_id[atom.subjob_id].append(Atom(
                atom.command_string,
                atom.expected_time,
                atom.actual_time,
                atom.exit_code,
                atom.state,
                atom.atom_id,
                atom.subjob_id
            ))

        subjobs = OrderedDict()
        for subjob in q_build_subjobs:
            atoms = atoms_by_subjob_id[subjob.subjob_id]
            # Add atoms after subjob is created so we don't alter their state on initialization
            subjob_to_add = Subjob(build_id, subjob.subjob_id, build.project_type, job_config, [])
            subjob_to_add._atoms = atoms
            subjob_to_add.completed = subjob.completed
            subjobs[subjob.subjob_id] = subjob_to_add
        build._all_subjobs_by_id = subjobs

        # Place subjobs into correct queues within the build
        build._unstarted_subjobs = Queue(maxsize=len(subjobs))
        build._finished_subjobs = Queue(maxsize=len(subjobs))
        for _, subjob in subjobs.items():
            if subjob.completed:
                build._finished_subjobs.put(subjob)
            else:
                build._unstarted_subjobs.put(subjob)

        # Spend preparation coin if this build is already completed
        if q_build_state.completed:
            build._preparation_coin.spend()

        # Build should be correctly deserialized
        return build

    def _get_query_build_object(self, build_id):
        """
        Query the database to build a series of SQLAlchemy objects related to the build.
        :param build_id: The id of the build to query from the database.
        """
        # Query for the build status associated with this `build_id`
        q_build_schema = self._session.query(BuildStateSchema) \
            .filter(BuildStateSchema.build_id == build_id) \
            .first()

        # Bulk query for tables that will return a single result each.
        # Returns tuple of (<BuildStateSchema>, <BuildMetaSchema>, <BuildRequestSchema>, ...)
        q_bulk_query = self._session.query(
            BuildStateSchema,
            BuildMetaSchema,
            BuildRequestSchema,
            BuildFsmSchema,
            BuildArtifactSchema
        ).filter(BuildRequestSchema.build_id == build_id) \
         .filter(BuildMetaSchema.build_id == build_id) \
         .filter(BuildFsmSchema.build_id == build_id) \
         .filter(BuildArtifactSchema.build_id == build_id) \
         .first()

        # Destruct results from query if we got a response
        q_build_state = q_bulk_query[0] if q_bulk_query else None
        q_build_meta = q_bulk_query[1] if q_bulk_query else None
        q_build_request = q_bulk_query[2] if q_bulk_query else None
        q_build_fsm = q_bulk_query[3] if q_bulk_query else None
        q_build_artifact = q_bulk_query[4] if q_bulk_query else None

        # Query for all `failed_artifact_directories` associated with this build
        q_failed_artifact_directories = self._session.query(FailedArtifactDirectoriesSchema) \
            .filter(FailedArtifactDirectoriesSchema.build_id == build_id) \
            .all()

        # Query for all `failed_subjob_atom_pairs` associated with this build
        q_failed_subjob_atom_pairs = self._session.query(FailedSubjobAtomPairsSchema) \
            .filter(FailedSubjobAtomPairsSchema.build_id == build_id) \
            .all()

        # Query for all the Atoms associated with this build
        q_build_atoms = self._session.query(AtomsSchema) \
            .filter(AtomsSchema.build_id == build_id) \
            .all()

        # Query for all the Subjobs associated with this build
        q_build_subjobs = self._session.query(SubjobsSchema) \
            .filter(SubjobsSchema.build_id == build_id) \
            .all()

        return (
            q_build_schema,
            q_build_state,
            q_build_meta,
            q_build_artifact,
            q_failed_artifact_directories,
            q_failed_subjob_atom_pairs,
            q_build_request,
            q_build_fsm,
            q_build_subjobs,
            q_build_atoms
        )


class IncompleteBuild(Exception):
    pass
