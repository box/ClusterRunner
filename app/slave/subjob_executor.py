import os
import shutil
import time

from app.master.build import BuildArtifact
from app.util.conf.configuration import Configuration
import app.util.fs as fs_util  # todo(joey): Rename util.py so we don't have package names conflicting with module names
from app.util import analytics, log, util


class SubjobExecutor(object):
    """
    This class represents a slave executor, responsible for executing subjobs on a slave.
    """
    def __init__(self, executor_id):
        """
        :type executor_id: int
        """
        self.id = executor_id
        self._project_type = None
        self._logger = log.get_logger(__name__)
        self._current_build_id = None
        self._current_subjob_id = None
        self._index_in_build = None

    def api_representation(self):
        """
        Gets a dict representing this resource that can be returned in an API response.
        :rtype: dict [str, mixed]
        """
        return {
            'id': self.id,
            'current_build': self._current_build_id,
            'current_subjob': self._current_subjob_id,
        }

    def configure_project_type(self, project_type_params):
        """
        Configure the project_type that this executor will use to execute subjobs. If there is alredy a previous
        project_type configured, tear it down.

        :type project_type_params: dict[str, str]
        """
        if self._project_type:
            self._project_type.teardown_executor()

        self._project_type = util.create_project_type(project_type_params)
        self._project_type.setup_executor()

    def run_job_config_setup(self):
        self._project_type.run_job_config_setup()

    def execute_subjob(self, build_id, subjob_id, atomic_commands, base_executor_index):
        """
        This is the method for executing a subjob. This performs the work required by executing the specified command,
        then archives the results into a single file and returns the filename.

        :type build_id: int
        :type subjob_id: int
        :type atomic_commands: list[str]
        :type base_executor_index: int
        :rtype: str
        """
        self._logger.info('Executing subjob (Build {}, Subjob {})...', build_id, subjob_id)

        # Set the current task
        self._current_build_id = build_id
        self._current_subjob_id = subjob_id

        # Maintain a list of atom artifact directories for compression and sending back to master
        atom_artifact_dirs = []

        # execute every atom and keep track of time elapsed for each
        for atom_id, atomic_command in enumerate(atomic_commands):
            atom_artifact_dir = BuildArtifact.atom_artifact_directory(
                build_id,
                subjob_id,
                atom_id,
                result_root=Configuration['artifact_directory']
            )

            # remove and recreate the atom artifact dir
            shutil.rmtree(atom_artifact_dir, ignore_errors=True)
            fs_util.create_dir(atom_artifact_dir)

            atom_environment_vars = {
                'ARTIFACT_DIR': atom_artifact_dir,
                'ATOM_ID': atom_id,
                'EXECUTOR_INDEX': self.id,  # Deprecated, use MACHINE_EXECUTOR_INDEX
                'MACHINE_EXECUTOR_INDEX': self.id,
                'BUILD_EXECUTOR_INDEX': base_executor_index + self.id,
            }

            atom_artifact_dirs.append(atom_artifact_dir)

            job_name = self._project_type.job_name
            atom_event_data = {'build_id': build_id, 'atom_id': atom_id, 'job_name': job_name, 'subjob_id': subjob_id}
            analytics.record_event(analytics.ATOM_START, **atom_event_data)

            exit_code = self._execute_atom_command(atomic_command, atom_environment_vars, atom_artifact_dir)

            atom_event_data['exit_code'] = exit_code
            analytics.record_event(analytics.ATOM_FINISH, **atom_event_data)

        # Generate mapping of atom directories (for archiving) to paths in the archive file
        targets_to_archive_paths = {atom_dir: os.path.basename(os.path.normpath(atom_dir))
                                    for atom_dir in atom_artifact_dirs}

        # zip file names must be unique for a build, so we append the subjob_id to the compressed file
        subjob_artifact_dir = BuildArtifact.build_artifact_directory(build_id,
                                                                     result_root=Configuration['artifact_directory'])
        tarfile_path = os.path.join(subjob_artifact_dir, 'results_{}.tar.gz'.format(subjob_id))
        fs_util.compress_directories(targets_to_archive_paths, tarfile_path)

        # Reset the current task
        self._current_build_id = None
        self._current_subjob_id = None

        return tarfile_path

    def kill(self):
        """
        Shutdown this executor. Kill any subprocesses the executor is currently executing.
        """
        if self._project_type:
            self._project_type.kill_subprocesses()

    def _execute_atom_command(self, atomic_command, atom_environment_vars, atom_artifact_dir):
        """
        Run the main command for this atom. Output the command, console output and exit code to
        files in the atom artifact directory. Return the exit code.

        :type atomic_command: str
        :type atom_environment_vars: dict[str, str]
        :type atom_artifact_dir: str
        :rtype: int
        """
        fs_util.create_dir(atom_artifact_dir)
        # This console_output_file must be opened in 'w+b' mode in order to be interchangeable with the
        # TemporaryFile instance that gets instantiated in self._project_type.execute_command_in_project.
        with open(os.path.join(atom_artifact_dir, BuildArtifact.OUTPUT_FILE), mode='w+b') as console_output_file:
            start_time = time.time()
            _, exit_code = self._project_type.execute_command_in_project(atomic_command, atom_environment_vars,
                                                                         output_file=console_output_file)
            elapsed_time = time.time() - start_time

        exit_code_output_path = os.path.join(atom_artifact_dir, BuildArtifact.EXIT_CODE_FILE)
        fs_util.write_file(str(exit_code) + '\n', exit_code_output_path)

        command_output_path = os.path.join(atom_artifact_dir, BuildArtifact.COMMAND_FILE)
        fs_util.write_file(str(atomic_command) + '\n', command_output_path)

        time_output_path = os.path.join(atom_artifact_dir, BuildArtifact.TIMING_FILE)
        fs_util.write_file('{:.2f}\n'.format(elapsed_time), time_output_path)

        return exit_code
