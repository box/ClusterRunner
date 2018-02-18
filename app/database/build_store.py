from collections import OrderedDict
import json
from typing import List, Optional

from app.database.connection import Connection
from app.database.schema import AtomsSchema, BuildSchema, FailedArtifactDirectoriesSchema, FailedSubjobAtomPairsSchema, SubjobsSchema
from app.master.build import Build
from app.master.build_fsm import BuildState
from app.util.log import get_logger


# pylint: disable=protected-access
class BuildStore:
    """
    Build storage service that stores and handles all builds.
    """
    _logger = get_logger(__name__)
    _cached_builds_by_id = OrderedDict()

    @classmethod
    def get(cls, build_id: int) -> Optional[Build]:
        """
        Returns a build by id.
        :param build_id: The id for the build whose status we are getting
        """
        build = cls._cached_builds_by_id.get(build_id)
        if build is None:
            cls._logger.debug('Requested build (id: {}) was not found in cache, checking database.'.format(build_id))
            build = Build.load_from_db(build_id)
            if build is not None:
                cls._cached_builds_by_id[build_id] = build

        return build

    @classmethod
    def get_range(cls, start: int, end: int) -> List[Build]:
        """
        Returns a list of all builds.
        :param start: The starting index of the requested build.
        :param end: 1 + the index of the last requested element, although if this is greater than the total number
                    of builds available the length of the returned list may be smaller than (end - start).
        """
        return [cls.get(build_id) for build_id in range(start + 1, end + 1)]

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
    def clean_up(cls):
        """
        Save current state of all cached builds.
        """
        with Connection.get() as session:
            cls._logger.notice('Executing clean up process.')
            for build_id in cls._cached_builds_by_id:
                build = cls._cached_builds_by_id[build_id]
                # As master shuts down, mark any uncompleted jobs as failed
                if build._status() != BuildState.FINISHED:
                    build.mark_failed('Master service was shut down before this build could complete.')
                build.save()

    @classmethod
    def _store_build(cls, build: Build) -> int:
        """
        Serialize a Build object and commit all of the parts to the database, and then
        return the build_id that was assigned after committing.
        :param build: The build to store into the database.
        """
        with Connection.get() as session:
            build_params = build._build_request._build_parameters
            fsm_timestamps = {state.lower(): timestamp for state, timestamp in build._state_machine.transition_timestamps.items()}
            build_artifact_dir = None
            if build._build_artifact is not None:
                build_artifact_dir = build._build_artifact.build_artifact_dir

            build_schema = BuildSchema(
                artifacts_tar_file=build._artifacts_tar_file,
                artifacts_zip_file=build._artifacts_zip_file,
                error_message=build._error_message,
                postbuild_tasks_are_finished=bool(build._postbuild_tasks_are_finished),
                setup_failures=build.setup_failures,
                timing_file_path=build._timing_file_path,
                build_artifact_dir=build_artifact_dir,
                build_parameters=json.dumps(build._build_request.build_parameters()),
                state=build._status(),
                queued_ts=fsm_timestamps['queued'],
                finished_ts=fsm_timestamps['finished'],
                prepared_ts=fsm_timestamps['prepared'],
                preparing_ts=fsm_timestamps['preparing'],
                error_ts=fsm_timestamps['error'],
                canceled_ts=fsm_timestamps['canceled'],
                building_ts=fsm_timestamps['building']
            )
            session.add(build_schema)

            # Commit this first to get the build_id created by the database
            # We use this build_id to store the other parts of a Build object
            session.commit()
            build_id = build_schema.build_id

            # FailedArtifactDirectories
            if build._build_artifact is not None:
                for directory in build._build_artifact._get_failed_artifact_directories():
                    failed_artifact_directories_schema = FailedArtifactDirectoriesSchema(
                        build_id=build_id,
                        failed_artifact_directory=directory
                    )
                    session.add(failed_artifact_directories_schema)

            # FailedSubjobAtomPairs
            if build._build_artifact is not None:
                for subjob_id, atom_id in build._build_artifact.get_failed_subjob_and_atom_ids():
                    failed_subjob_atom_pairs_schema = FailedSubjobAtomPairsSchema(
                        build_id=build_id,
                        subjob_id=subjob_id,
                        atom_id=atom_id
                    )
                    session.add(failed_subjob_atom_pairs_schema)

            # Subjobs
            subjobs = build._all_subjobs_by_id
            for subjob_id in subjobs:
                subjob = build._all_subjobs_by_id[subjob_id]
                subjob_schema = SubjobsSchema(
                    subjob_id=subjob_id,
                    build_id=build_id,
                    completed=subjob.completed
                )
                session.add(subjob_schema)

                # Atoms
                for atom in subjob._atoms:  # pylint: disable=protected-access
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
                    session.add(atom_schema)

            return build_id

    @classmethod
    def count_all_builds(cls) -> int:
        """
        Return the total amount of builds stored in the database.
        """
        with Connection.get() as session:
            return session.query(BuildSchema).count()
