import json
import os

from app.master.subjob import Subjob
import app.util.fs
from app.util.log import get_logger


class BuildArtifact(object):
    ATOM_ARTIFACT_DIR_PREFIX = 'artifact_'

    def __init__(self, build_artifact_dir):
        """
        :param build_artifact_dir: absolute path to the build artifact (IE: '/var/clusterrunner/artifacts/20')
        :type build_artifact_dir: str
        """
        self._logger = get_logger(__name__)
        self.build_artifact_dir = build_artifact_dir
        self._failed_commands = None

    def write_timing_data(self, timing_file_path, timing_data):
        """
        Persist timing data to a file.

        If there is no timing data, write the timing file regardless of whether there were any invalid executions.
        If there is timing data, only write the timing file if there were no failures.

        :param timing_file_path: where the timing data should be written
        :type timing_file_path: str
        :param timing_data: the key-value pairs of the atom-time in seconds the atom took to run
        :type timing_data: dict[str, float]
        """
        if len(timing_data) == 0:
            self._logger.error('Failed to find timing data')
            return

        app.util.fs.create_dir(os.path.dirname(timing_file_path))

        # If file doesn't exist, then write timing data no matter what
        if not os.path.isfile(timing_file_path):
            self._write_timing_data_to_file(timing_file_path, timing_data)
            self._logger.debug('Created new timing file in {}', timing_file_path)
            return

        # If file exists, only overwrite timing data if there were no failures this build
        if len(self.get_failed_commands()) == 0:
            self._write_timing_data_to_file(timing_file_path, timing_data)
            self._logger.debug('Overwrote existing timing file in {}', timing_file_path)
            return

        self._logger.debug('Did not write/overwrite timing data during build')

    def get_failed_commands(self):
        """
        :return: a dictionary of atom names (e.g. artifact_0_0) to failed commmands
        :rtype dict of [str, str]
        """
        if self._failed_commands is None:

            if not os.path.isdir(self.build_artifact_dir):
                message = 'Build artifact dir {} does not exist'.format(self.build_artifact_dir)
                self._logger.error(message)
                raise RuntimeError(message)

            # Find failed atoms in the artifact directory
            self._failed_commands = {}
            for build_artifact_file_or_subdir in os.listdir(self.build_artifact_dir):
                if self._is_atom_artifact_dir(build_artifact_file_or_subdir):
                    exit_file = os.path.join(self.build_artifact_dir, build_artifact_file_or_subdir, Subjob.EXIT_CODE_FILE)
                    command_file = os.path.join(self.build_artifact_dir, build_artifact_file_or_subdir, Subjob.COMMAND_FILE)
                    if os.path.isfile(exit_file) and os.path.isfile(command_file):
                        with open(exit_file, 'r') as exit_stream, open(command_file, 'r') as command_stream:
                            exit_code = exit_stream.readline()
                            command = command_stream.readline()
                            if int(exit_code) != 0:
                                self._failed_commands[build_artifact_file_or_subdir] = command
                    else:
                        self._logger.error("Missing clusterrunner artifacts for " + build_artifact_file_or_subdir)

        return self._failed_commands

    def _is_atom_artifact_dir(self, dir_basename):
        """
        :param dir_basename: the basename of the directory
        :type dir_basename: str
        :return: true if the directory name is an artifact directory
        :rtype: bool
        """
        return dir_basename.startswith(BuildArtifact.ATOM_ARTIFACT_DIR_PREFIX)

    def generate_failures_file(self):
        """
        Only generate a failures.txt file if there were any failed commands for the build.
        """
        failed_atoms = self.get_failed_commands()
        if len(failed_atoms) > 0:
            with open(os.path.join(self.build_artifact_dir, 'failures.txt'), 'w') as f:
                f.write("\n".join(failed_atoms))

    def _write_timing_data_to_file(self, path, timing_data):
        """
        :type path: str
        :type timing_data: dict[str, float]
        """
        app.util.fs.write_file(json.dumps(timing_data), path)
