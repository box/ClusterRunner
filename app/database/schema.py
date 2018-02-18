from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


class BuildSchema(Base):
    """Describes attributes on a build"""
    __tablename__ = 'builds'

    build_id = Column(Integer, primary_key=True, autoincrement=True)
    artifacts_tar_file = Column(String)
    artifacts_zip_file = Column(String)
    error_message = Column(String)
    postbuild_tasks_are_finished = Column(String)
    setup_failures = Column(Integer)
    timing_file_path = Column(String)
    build_artifact_dir = Column(String)
    build_parameters = Column(String)
    state = Column(String)
    queued_ts = Column(Float)
    finished_ts = Column(Float)
    prepared_ts = Column(Float)
    preparing_ts = Column(Float)
    error_ts = Column(Float)
    canceled_ts = Column(Float)
    building_ts = Column(Float)


class FailedArtifactDirectoriesSchema(Base):
    """Describes the list of _failed_artifact_directories (List[str]) from BuildArtifact"""
    __tablename__ = 'failed_artifact_directories'

    id = Column(Integer, primary_key=True, autoincrement=True)
    build_id = Column(Integer, ForeignKey('builds.build_id'))
    failed_artifact_directory = Column(String)


class FailedSubjobAtomPairsSchema(Base):
    """Describes the list of _failed_subjob_atom_pairs (List[int, int]) from BuildArtifact"""
    __tablename__ = 'failed_subjobs_atom_pairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    build_id = Column(Integer, ForeignKey('builds.build_id'))
    subjob_id = Column(Integer)
    atom_id = Column(Integer)


class SubjobsSchema(Base):
    """Describes the subjobs associated with a Build"""
    __tablename__ = 'subjobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    subjob_id = Column(Integer)
    build_id = Column(Integer, ForeignKey('builds.build_id'))
    completed = Column(Boolean)


class AtomsSchema(Base):
    """Describes the subjobs associated with a Build"""
    __tablename__ = 'atoms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    atom_id = Column(Integer)
    build_id = Column(Integer, ForeignKey('builds.build_id'))
    subjob_id = Column(Integer)
    command_string = Column(String)
    expected_time = Column(Float)
    actual_time = Column(Float)
    exit_code = Column(Integer)
    state = Column(String)
