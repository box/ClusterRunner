import sqlite3


class FailedSQLiteTableSetup(Exception):
    pass


class DatabaseSetup():
    _builds_query = """CREATE TABLE IF NOT EXISTS builds (
        build_id INTEGER PRIMARY KEY,
        completed BOOLEAN
    )"""

    _build_metas_query = """CREATE TABLE IF NOT EXISTS build_metas (
        build_id INTEGER PRIMARY KEY,
        artifacts_tar_file TEXT,
        artifacts_zip_file TEXT,
        error_message TEXT,
        postbuild_tasks_are_finished TEXT,
        setup_failures INTEGER,
        timing_file_path TEXT
    )"""

    _build_artifacts_query = """CREATE TABLE IF NOT EXISTS build_artifacts (
        build_id INTEGER,
        build_artifact_dir TEXT
    )"""

    _failed_artifact_directories_query = """CREATE TABLE IF NOT EXISTS failed_artifact_directories (
        uid INTEGER PRIMARY KEY,
        build_id INTEGER,
        failed_artifact_directory TEXT
    )"""

    _failed_subjob_atom_pairs_query = """CREATE TABLE IF NOT EXISTS failed_subjobs_atom_pairs (
        uid INTEGER PRIMARY KEY,
        build_id INTEGER,
        subjob_id INTEGER,
        atom_id INTEGER
    )"""

    _build_requests_query = """CREATE TABLE IF NOT EXISTS build_requests (
        build_id INTEGER PRIMARY KEY,
        type STRING,
        url STRING,
        branch STRING,
        job_name STRING
    )"""

    _build_fsm_query = """CREATE TABLE IF NOT EXISTS build_fsms (
        build_id INTEGER PRIMARY KEY,
        state TEXT,
        queued REAL,
        finished REAL,
        prepared REAL,
        preparing REAL,
        error REAL,
        canceled REAL,
        building REAL
    )"""

    _subjobs_query = """CREATE TABLE IF NOT EXISTS subjobs (
        uid INTEGER PRIMARY KEY,
        subjob_id INTEGER,
        completed BOOLEAN,
        build_id INTEGER
    )"""

    _atoms_query = """CREATE TABLE IF NOT EXISTS atoms (
        uid INTEGER PRIMARY KEY,
        atom_id INTEGER,
        build_id INTEGER,
        subjob_id INTEGER,
        command_string TEXT,
        expected_time REAL,
        actual_time REAL,
        exit_code INTEGER,
        state TEXT
    )"""

    @classmethod
    def prepare(cls):
        print('Preparing SQLite tables...')
        sqlite_connection = sqlite3.connect('clusterrunner.db')
        sqlite_cursor = sqlite_connection.cursor()
        sqlite_cursor.execute(cls._builds_query)
        sqlite_cursor.execute(cls._build_metas_query)
        sqlite_cursor.execute(cls._build_artifacts_query)
        sqlite_cursor.execute(cls._failed_artifact_directories_query)
        sqlite_cursor.execute(cls._failed_subjob_atom_pairs_query)
        sqlite_cursor.execute(cls._build_requests_query)
        sqlite_cursor.execute(cls._build_fsm_query)
        sqlite_cursor.execute(cls._subjobs_query)
        sqlite_cursor.execute(cls._atoms_query)
        sqlite_connection.commit()
        sqlite_connection.close()
        print('...done')

    @classmethod
    def reset(cls):
        print('Resetting SQLite tables...')
        sqlite_connection = sqlite3.connect('clusterrunner.db')
        sqlite_cursor = sqlite_connection.cursor()
        try:
            sqlite_cursor.execute('DROP TABLE IF EXISTS builds')
            sqlite_cursor.execute('DROP TABLE IF EXISTS build_metas')
            sqlite_cursor.execute('DROP TABLE IF EXISTS build_artifacts')
            sqlite_cursor.execute('DROP TABLE IF EXISTS failed_artifact_directories')
            sqlite_cursor.execute('DROP TABLE IF EXISTS failed_subjobs_atom_pairs')
            sqlite_cursor.execute('DROP TABLE IF EXISTS build_requests')
            sqlite_cursor.execute('DROP TABLE IF EXISTS build_fsms')
            sqlite_cursor.execute('DROP TABLE IF EXISTS subjobs')
            sqlite_cursor.execute('DROP TABLE IF EXISTS atoms')
            sqlite_cursor.execute(cls._builds_query)
            sqlite_cursor.execute(cls._build_metas_query)
            sqlite_cursor.execute(cls._build_artifacts_query)
            sqlite_cursor.execute(cls._failed_artifact_directories_query)
            sqlite_cursor.execute(cls._failed_subjob_atom_pairs_query)
            sqlite_cursor.execute(cls._build_requests_query)
            sqlite_cursor.execute(cls._build_fsm_query)
            sqlite_cursor.execute(cls._subjobs_query)
            sqlite_cursor.execute(cls._atoms_query)
            sqlite_connection.commit()
            sqlite_connection.close()
            print('...done')
        except:
            print('...failed')
            raise FailedSQLiteTableSetup
