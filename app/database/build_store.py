from collections import OrderedDict
from itertools import islice
from queue import Queue
from sqlalchemy import func
from typing import List, Optional, Tuple

from app.database.connection import Connection
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


class BuildStore:
    """
    Build storage service that stores and handles all builds.
    """
    _logger = get_logger(__name__)
    _cached_builds_by_id = OrderedDict()
    _session = Connection.get()

    @classmethod
    def get(cls, build_id: int) -> Optional[Build]:
        """
        Returns a build by id
        :param build_id: The id for the build whose status we are getting
        """
        build = cls._cached_builds_by_id.get(build_id)
        if build is None:
            cls._logger.info('Requested build (id: {}) was not found in cache, checking database.'.format(build_id))
            build = cls._reconstruct_build(build_id)
            if build is not None:
                cls._cached_builds_by_id[build_id] = build
                cls._logger.notice('Build (id: {}) was added to cache.'.format(build_id))

        return build

    @classmethod
    def get_range(cls, start: int, end: int) -> List['Build']:
        """
        Returns a list of all builds.
        :param start: The starting index of the requested build
        :param end: The number of builds requested
        """
        requested_builds = islice(cls._cached_builds_by_id, start, end)
        return [cls._cached_builds_by_id[key] for key in requested_builds]

    @classmethod
    def add(cls, build: Build):
        """
        Add new build to collection.
        :param build: The build to add to the store.
        """
        build_id = cls._store_build(build)
        build._build_id = build_id
        cls._cached_builds_by_id[build_id] = build

    @classmethod
    def save(cls, build: Build):
        """
        Save current state of given build. 
        We assume that this build already exists in the database. You should always call `add` before
        trying to ever call a `save`. This should be done for you in cluster_master.
        We also assume this build is already in the cache in its current state.
        :param build: The build to save to database.
        """
        cls._logger.notice('Saving build (id: {}) in database.'.format(build.build_id()))
        cls._update_build(build)
        print('ORIGINAL -- SAVED')
        print(str(build))

    @classmethod
    def clean_up(cls):
        """
        Save current state of all cached builds.
        """
        for build_id in cls._cached_builds_by_id:
            build = cls._cached_builds_by_id[build_id]
            cls._update_build(build)
            print('ORIGINAL -- CLEAN UP ON SHUTDOWN')
            print(str(build))
        cls._session.commit()

    @classmethod
    def size(cls) -> Tuple[int, int]:
        """
        Return a tuple of both the amount of builds cached within memory and the
        total amount of builds stored in the database
        """
        total_len = cls._session.query(func.count('*')).select_from(BuildStateSchema).scalar()
        cached_len = len(cls._cached_builds_by_id)
        return cached_len

    @classmethod
    def _store_build(cls, build: Build) -> int:
        """
        Serialize a Build object and commit all of the parts to the database, and then
        return the build_id that was assigned after committing.
        """
        # Build Status
        build_schema = BuildStateSchema(
            completed=build._status() == BuildState.FINISHED,
            prepared=build._status() == BuildState.PREPARED
        )
        cls._session.add(build_schema)

        # Commit this first to get the build_id created by the database
        # We use this build_id to store the other parts of a Build object
        cls._session.commit()
        build_id = build_schema.build_id

        # Build Meta
        build_meta = BuildMetaSchema(
            build_id = build_id,
            artifacts_tar_file = build._artifacts_tar_file,
            artifacts_zip_file = build._artifacts_zip_file,
            error_message = build._error_message,
            postbuild_tasks_are_finished = build._postbuild_tasks_are_finished,
            timing_file_path = build._timing_file_path,
            setup_failures = build.setup_failures
        )
        cls._session.add(build_meta)

        # BuildArtifacts
        build_artifact_dir = None
        if build._build_artifact is not None:
            build_artifact_dir = build._build_artifact.build_artifact_dir
        build_artifacts = BuildArtifactSchema(
            build_id = build_id,
            build_artifact_dir = build_artifact_dir
        )
        cls._session.add(build_artifacts)

        # FailedArtifactDirectories
        if build._build_artifact is not None:
            for directory in build._build_artifact._get_failed_artifact_directories():
                failed_artifact_directory = FailedArtifactDirectoriesSchema(
                    build_id = build_id,
                    failed_artifact_directory = directory
                )
                cls._session.add(failed_artifact_directory)
        
        # FailedSubjobAtomPairs
        if build._build_artifact is not None:
            for subjob_id, atom_id in build._build_artifact.get_failed_subjob_and_atom_ids():
                failed_subjob_and_atom_ids = FailedSubjobAtomPairsSchema(
                    build_id = build_id,
                    subjob_id = subjob_id,
                    atom_id = atom_id
                )
                cls._session.add(failed_subjob_and_atom_ids)

        # BuildRequest
        build_params = build._build_request._build_parameters
        build_request = BuildRequestSchema(
            build_id = build_id,
            type = build_params.get('type'),
            url = build_params.get('url'),
            branch = build_params.get('branch'),
            job_name = build_params.get('job_name')
        )
        cls._session.add(build_request)
        
        # BuildFsm
        fsm_timestamps = {state.lower(): timestamp for state, timestamp in build._state_machine.transition_timestamps.items()}
        build_fsm = BuildFsmSchema(
            build_id = build_id,
            state = build._status(),
            queued = fsm_timestamps['queued'],
            finished = fsm_timestamps['finished'],
            prepared = fsm_timestamps['prepared'],
            preparing = fsm_timestamps['preparing'],
            error = fsm_timestamps['error'],
            canceled = fsm_timestamps['canceled'],
            building = fsm_timestamps['building']
        )
        cls._session.add(build_fsm)

        # Subjobs
        subjobs = build._all_subjobs_by_id
        for subjob_id in subjobs:
            subjob = build._all_subjobs_by_id[subjob_id]
            subjob_schema = SubjobsSchema(
                subjob_id = subjob_id,
                build_id = build_id,
                completed = subjob.completed
            )
            cls._session.add(subjob_schema)

            # Atoms
            for atom in subjob._atoms:
                atom_schema = AtomsSchema(
                    atom_id = atom.id,
                    build_id = build_id,
                    subjob_id = subjob_id,
                    command_string = atom.command_string,
                    expected_time = atom.expected_time,
                    actual_time = atom.actual_time,
                    exit_code = atom.exit_code,
                    state = atom.state,
                )
                cls._session.add(atom_schema)

        # Save changes
        cls._session.commit()
        return build_id

    @classmethod
    def _update_build(cls, build: Build) -> int:
        """
        Serialize a Build object and update all of the parts to the database.
        NOTE: These changes are not committed here. If you want these changes to persist, 
              make sure to commit the session afterwards.
              We do selectively call commit a few times here but only after we delete rows.
        """
        build_id = build.build_id()

        # Query for the build status associated with this `build_id`
        q_build_schema = cls._session.query(BuildStateSchema)\
            .filter(BuildStateSchema.build_id == build_id)\
            .first()

        # If this wasn't found, it's safe to assume that the build doesn't exist within the database
        if q_build_schema is None:
            raise ItemNotFoundError('Unable to find in database build with id: {}.'.format(build_id))

        q_build_schema.completed = build._status() == BuildState.FINISHED
        q_build_schema.prepared = build._status() != BuildState.PREPARING

        # Query for the basic build attributes associated with this `build_id`
        q_build_meta = cls._session.query(BuildMetaSchema)\
            .filter(BuildMetaSchema.build_id == build_id)\
            .first()

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

        build_artifact = cls._session.query(BuildArtifactSchema)\
            .filter(BuildArtifactSchema.build_id == build_id)\
            .first()

        build_artifact.build_artifact_dir = build_artifact_dir

        # Query for the FailedArtifactDirectories associated with this `build_id`
        if build._build_artifact is not None:
            # Clear all old directories associated with this `build_id`
            cls._session.query(FailedArtifactDirectoriesSchema)\
               .filter(FailedArtifactDirectoriesSchema.build_id == build_id)\
               .delete()

            # Commit changes so we don't delete the newly added rows later
            cls._session.commit()

            # Add all the updated versions of the directories
            for directory in build._build_artifact._get_failed_artifact_directories():
                failed_artifact_directory = FailedArtifactDirectoriesSchema(
                    build_id = build_id,
                    failed_artifact_directory = directory
                )
                cls._session.add(failed_artifact_directory)

        # Query for the FailedSubjobAtomPairs associated with this `build_id`
        if build._build_artifact is not None:
            # Clear all old data associated with this build_id
            cls._session.query(FailedSubjobAtomPairsSchema) \
               .filter(FailedSubjobAtomPairsSchema.build_id == build_id) \
               .delete()

            # Commit changes so we don't delete the newly added rows later
            cls._session.commit()

            # Add all the updated versions of the data
            for subjob_id, atom_id in build._build_artifact.get_failed_subjob_and_atom_ids():
                failed_subjob_and_atom_ids = FailedSubjobAtomPairsSchema(
                    build_id = build_id,
                    subjob_id = subjob_id,
                    atom_id = atom_id
                )
                cls._session.add(failed_subjob_and_atom_ids)

        # BuildRequest
        build_request = cls._session.query(BuildRequestSchema)\
            .filter(BuildRequestSchema.build_id == build_id)\
            .first()

        build_params = build._build_request._build_parameters
        build_request.type = build_params.get('type')
        build_request.url = build_params.get('url')
        build_request.branch = build_params.get('branch')
        build_request.job_name = build_params.get('job_name')

        # BuildFsm
        build_fsm = cls._session.query(BuildFsmSchema)\
            .filter(BuildFsmSchema.build_id == build_id)\
            .first()

        fsm_timestamps = {state.lower(): timestamp for state, timestamp in build._state_machine.transition_timestamps.items()}
        build_fsm.state = build._status()
        build_fsm.queued = fsm_timestamps['queued']
        build_fsm.finished = fsm_timestamps['finished']
        build_fsm.prepared = fsm_timestamps['prepared']
        build_fsm.preparing = fsm_timestamps['preparing']
        build_fsm.error = fsm_timestamps['error']
        build_fsm.canceled = fsm_timestamps['canceled']
        build_fsm.building = fsm_timestamps['building']
        cls._session.add(build_fsm)

        # Subjobs
        # Clear all old Subjobs and Atoms associated with this `build_id`
        cls._session.query(SubjobsSchema)\
            .filter(SubjobsSchema.build_id == build_id)\
            .delete()
        cls._session.query(AtomsSchema)\
            .filter(AtomsSchema.build_id == build_id)\
            .delete()

        # Commit changes so we don't delete the newly added rows later
        cls._session.commit()

        # Add all the updated versions of Subjobs and Atoms
        subjobs = build._all_subjobs_by_id
        for subjob_id in subjobs:
            subjob = build._all_subjobs_by_id[subjob_id]
            subjob_schema = SubjobsSchema(
                subjob_id = subjob_id,
                build_id = build_id,
                completed = subjob.completed
            )
            cls._session.add(subjob_schema)

            # Atoms
            for atom in subjob._atoms:
                atom_schema = AtomsSchema(
                    atom_id = atom.id,
                    build_id = build_id,
                    subjob_id = subjob_id,
                    command_string = atom.command_string,
                    expected_time = atom.expected_time,
                    actual_time = atom.actual_time,
                    exit_code = atom.exit_code,
                    state = atom.state
                )
                cls._session.add(atom_schema)

    @classmethod
    def _reconstruct_build(cls, build_id):

        # Bulk query for tables that will return a single result each.
        # Returns tuple of (<BuildMetaSchema>, <BuildRequestSchema>, ...)
        bulk_query = cls._session.query(
            BuildMetaSchema,
            BuildRequestSchema,
            BuildFsmSchema,
            BuildArtifactSchema
        ).filter(BuildRequestSchema.build_id == build_id)\
         .filter(BuildMetaSchema.build_id == build_id)\
         .filter(BuildFsmSchema.build_id == build_id)\
         .filter(BuildArtifactSchema.build_id == build_id)\
         .first()

        # No results, build wasn't found in database
        if not bulk_query:
            return None

        q_build_meta = bulk_query[0]
        q_build_request = bulk_query[1]
        q_build_fsm = bulk_query[2]
        q_build_artifact = bulk_query[3]

        # Genereate a BuildRequest object with our query response
        build_request = BuildRequest({
            'type': q_build_request.type,
            'url': q_build_request.url,
            'branch': q_build_request.branch,
            'job_name': q_build_request.job_name
        })

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
        build._postbuild_tasks_are_finished = q_build_meta.postbuild_tasks_are_finished
        build.setup_failures = q_build_meta.setup_failures
        build._timing_file_path = q_build_meta.timing_file_path

        # Manually set the state machine timestamps
        build._state_machine._transition_timestamps = {
            'queued': q_build_fsm.queued,
            'finished': q_build_fsm.finished,
            'prepared': q_build_fsm.prepared,
            'preparing': q_build_fsm.preparing,
            'error': q_build_fsm.error,
            'canceled': q_build_fsm.canceled,
            'building': q_build_fsm.building
        }
        build._state_machine._fsm.current = q_build_fsm.state

        # Create the `build_artifact`, we will be altering its attributes as we get more data
        build_artifact = BuildArtifact(q_build_artifact.build_artifact_dir)
        
        # Query for all `failed_artifact_directories` associated with this build
        q_failed_artifact_directories = cls._session.query(FailedArtifactDirectoriesSchema)\
            .filter(FailedArtifactDirectoriesSchema.build_id == build_id)\
            .all()
        
        directories = []
        for directory in q_failed_artifact_directories:
            directories.append(directory.failed_artifact_directory)
        build_artifact._failed_artifact_directories = directories

        # Query for all `failed_subjob_atom_pairs` associated with this build
        failed_subjob_atom_pairs = cls._session.query(FailedSubjobAtomPairsSchema)\
            .filter(FailedSubjobAtomPairsSchema.build_id == build_id)\
            .all()

        pairs = []
        for pair in failed_subjob_atom_pairs:
            pairs.append((pair.subjob_id, pair.atom_id))
        build_artifact._failed_subjob_atom_pairs = pairs

        # The `build_artifact` is prepared, so manually assign it to build
        build._build_artifact = build_artifact
        
        # Query for all the Atoms associated with this build
        build_atoms = cls._session.query(AtomsSchema)\
            .filter(AtomsSchema.build_id == build_id)\
            .all()

        atoms_by_subjob_id = {}
        for atom in build_atoms:
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

        # Query for all the Subjobs associated with this build
        build_subjobs = cls._session.query(SubjobsSchema)\
            .filter(SubjobsSchema.build_id == build_id)\
            .all()

        subjobs = OrderedDict()
        for subjob in build_subjobs:
            atoms = atoms_by_subjob_id[subjob.subjob_id]
            # ATOMS STATE GETS RESET TO `NOT_STARTED` HERE
            subjob_to_add = Subjob(build_id, subjob.subjob_id, build.project_type, job_config, atoms)
            subjob_to_add.completed = subjob.completed
            subjobs[subjob.subjob_id] = subjob_to_add
        build._all_subjobs_by_id = subjobs

        # Place subjobs into correct queues within the build
        build._unstarted_subjobs = Queue(maxsize=len(subjobs))
        build._finished_subjobs = Queue(maxsize=len(subjobs))
        for _, subjob in subjobs.items():
            build._finished_subjobs.put(subjob) if subjob.completed else build._unstarted_subjobs.put(subjob)

        # Build should be correctly deserialized
        return build


class SQLAlchemyQueryFailed(Exception):
    pass
