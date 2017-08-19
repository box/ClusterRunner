from sqlalchemy import Column, Integer, String, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


class BuildStateSchema(Base):
    """Describes the state of a Build"""
    __tablename__ = 'builds'

    build_id = Column(Integer, primary_key=True, autoincrement=True)
    completed = Column(Boolean)


class BuildMetaSchema(Base):
    """Describes all the Build attributes that are basic datatypes"""
    __tablename__ = 'build_metas'

    build_id = Column(Integer, primary_key=True)
    artifacts_tar_file = Column(String)
    artifacts_zip_file = Column(String)
    error_message = Column(String)
    postbuild_tasks_are_finished = Column(String)
    setup_failures = Column(Integer)
    timing_file_path = Column(String)
    # call `self.generate_project_type()` after init


class BuildArtifactSchema(Base):
    """Describes the _build_artifact attribute of a Build"""
    __tablename__ = 'build_artifacts'

    build_id = Column(Integer, primary_key=True)
    build_artifact_dir = Column(String)


class FailedArtifactDirectoriesSchema(Base):
    """Describes the list of _failed_artifact_directories (List[str]) from BuildArtifact"""
    __tablename__ = 'failed_artifact_directories'

    uid = Column(Integer, primary_key=True, autoincrement=True)
    build_id = Column(Integer)
    failed_artifact_directory = Column(String)


class FailedSubjobAtomPairsSchema(Base):
    """Describes the list of _failed_subjob_atom_pairs (List[int, int]) from BuildArtifact"""
    __tablename__ = 'failed_subjobs_atom_pairs'

    uid = Column(Integer, primary_key=True, autoincrement=True)
    build_id = Column(Integer)
    subjob_id = Column(Integer)
    atom_id = Column(Integer)


class BuildRequestSchema(Base):
    """Describes the build_request attribute of a Build. Use these values to initialize a BuildRequest object."""
    __tablename__ = 'build_requests'

    build_id = Column(Integer, primary_key=True)
    build_parameters = Column(String)


class BuildFsmSchema(Base):
    """Describes the _state_machine in a Build Object"""
    __tablename__ = 'build_fsms'

    build_id = Column(Integer, primary_key=True)
    state = Column(String)
    queued = Column(Float)
    finished = Column(Float)
    prepared = Column(Float)
    preparing = Column(Float)
    error = Column(Float)
    canceled = Column(Float)
    building = Column(Float)


# project_type = build.generate_project_type()
# job_config = self.project_type.job_config()
# Subjob(build_id, subjob_id, project_type, job_config, atoms)
# ^-- this will set all the atoms to `NOT_STARTED` fyi
class SubjobsSchema(Base):
    """Describes the subjobs associated with a Build"""
    __tablename__ = 'subjobs'

    uid = Column(Integer, primary_key=True, autoincrement=True)
    subjob_id = Column(Integer)
    build_id = Column(Integer)
    completed = Column(Boolean)


class AtomsSchema(Base):
    """Describes the subjobs associated with a Build"""
    __tablename__ = 'atoms'

    uid = Column(Integer, primary_key=True, autoincrement=True)
    atom_id = Column(Integer)
    build_id = Column(Integer)
    subjob_id = Column(Integer)
    command_string = Column(String)
    expected_time = Column(Float)
    actual_time = Column(Float)
    exit_code = Column(Integer)
    state = Column(String)
