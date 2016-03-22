import json
import os
import re

from app.util.conf.configuration import Configuration
import app.util.fs
from app.util.log import get_logger


class BuildArtifact(object):
    ATOM_ARTIFACT_DIR_PREFIX = 'artifact_'
    ATOM_DIR_FORMAT = ATOM_ARTIFACT_DIR_PREFIX + '{}_{}'
    COMMAND_FILE = 'clusterrunner_command'
    EXIT_CODE_FILE = 'clusterrunner_exit_code'
    OUTPUT_FILE = 'clusterrunner_console_output'
    TIMING_FILE = 'clusterrunner_time'
    ARTIFACT_FILE_NAME = 'results.tar.gz'

    def __init__(self, build_artifact_dir):
        """
        :param build_artifact_dir: absolute path to the build artifact (IE: '/var/clusterrunner/artifacts/20')
        :type build_artifact_dir: str
        """
        self._logger = get_logger(__name__)
        self.build_artifact_dir = build_artifact_dir
        self._failed_artifact_directories = None
        self._failed_subjob_atom_pairs = None

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

        # If file exists, update the timing data only if there were no failures this build
        # @TODO: in the future we should always update the timing data, but only for passed atom keys.
        if len(self._get_failed_artifact_directories()) == 0:
            self._update_timing_file(timing_file_path, timing_data)
            self._logger.debug('Overwrote existing timing file in {}', timing_file_path)
            return

        self._logger.debug('Did not write/overwrite timing data during build')

    def get_failed_subjob_and_atom_ids(self):
        """
        Get a list of (subjob_id, atom_id) tuples that failed.
        :return: Returns a list of tuples with two integers.
        :rtype: list[(int, int)]
        """
        if self._failed_subjob_atom_pairs is None:
            self._failed_subjob_atom_pairs = []

            for failed_artifact_dir in self._get_failed_artifact_directories():
                self._failed_subjob_atom_pairs.append(self._subjob_and_atom_ids(failed_artifact_dir))

        return self._failed_subjob_atom_pairs

    def _get_failed_artifact_directories(self):
        """
        :return: A list of build-artifact relative paths to the failed artifact directories (e.g. artifact_0_0).
        :rtype list[str]
        """
        if self._failed_artifact_directories is None:
            if not os.path.isdir(self.build_artifact_dir):
                message = 'Build artifact dir {} does not exist'.format(self.build_artifact_dir)
                self._logger.error(message)
                raise RuntimeError(message)

            # Find failed atoms in the artifact directory
            self._failed_artifact_directories = []
            for build_artifact_file_or_subdir in os.listdir(self.build_artifact_dir):
                if self._is_atom_artifact_dir(build_artifact_file_or_subdir):
                    exit_file = os.path.join(self.build_artifact_dir, build_artifact_file_or_subdir,
                                             BuildArtifact.EXIT_CODE_FILE)
                    if os.path.isfile(exit_file):
                        with open(exit_file, 'r') as exit_stream:
                            exit_code = exit_stream.readline()
                            if int(exit_code) != 0:
                                self._failed_artifact_directories.append(build_artifact_file_or_subdir)
                    else:
                        self._logger.error("Missing clusterrunner exit file for " + build_artifact_file_or_subdir)

        return self._failed_artifact_directories

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
        failed_atom_directories = self._get_failed_artifact_directories()
        if len(failed_atom_directories) > 0:
            with open(os.path.join(self.build_artifact_dir, 'failures.txt'), 'w') as f:
                f.write("\n".join(failed_atom_directories))

    def _write_timing_data_to_file(self, timing_file_path, timing_data):
        """
        :type timing_file_path: str
        :type timing_data: dict[str, float]
        """
        app.util.fs.write_file(json.dumps(timing_data), timing_file_path)

    def _update_timing_file(self, timing_file_path, new_timing_data):
        """
        Update the timing data for the atoms specified in new_timing_data. This means that new results
        does not replace the entire timing data file, but rather only replaces the timing data for
        individual atom keys.
        :param timing_file_path: str
        :param new_timing_data: dict[str, float]
        """
        with open(timing_file_path) as timing_file:
            timing_data = json.load(timing_file)

        timing_data.update(new_timing_data)
        self._write_timing_data_to_file(timing_file_path, timing_data)

    @staticmethod
    def atom_artifact_directory(build_id, subjob_id, atom_id, result_root=None):
        """
        Get the sys path to the atom artifact directory.

        :type build_id: int
        :type subjob_id: int
        :type atom_id: int
        :param result_root: The sys path to the result directory that isn't the default artifact directory.
        :type result_root: str | None
        :rtype: str
        """
        return BuildArtifact._artifact_directory(build_id, subjob_id=subjob_id, atom_id=atom_id,
                                                 result_root=result_root)

    @staticmethod
    def build_artifact_directory(build_id, result_root=None):
        """
        Get the sys path to the build artifact directory.

        :type build_id: int
        :param result_root: The sys path to the result directory that isn't the default artifact directory.
        :type result_root: str | None
        :rtype: str
        """
        return BuildArtifact._artifact_directory(build_id, result_root=result_root)

    @staticmethod
    def _artifact_directory(build_id, subjob_id=None, atom_id=None, result_root=None):
        """
        To get the full path to an atom artifact id, the caller must specify all id's: build_id, subjob_id, atom_id.
        To get the path to just the build artifact directory, the caller must only specify the build_id.

        If the caller specifies exactly one of the subjob_id or atom_id, it is a fatal error, and this method
        will raise a ValueError exception.

        :type build_id: int
        :type subjob_id: int | None
        :type atom_id: int | None
        :param result_root: The sys path to the result directory that isn't the default artifact directory.
        :type result_root: str | None
        :rtype: str
        """
        result_root = result_root if result_root is not None else Configuration['artifact_directory']

        if subjob_id is None and atom_id is None:
            return os.path.join(result_root, str(build_id))
        elif subjob_id is not None and atom_id is not None:
            return os.path.join(result_root, str(build_id), BuildArtifact.ATOM_DIR_FORMAT.format(subjob_id, atom_id))
        else:
            raise ValueError('Specified one of either subjob_id or atom_id. Must either specify both or neither.')

    @staticmethod
    def _subjob_and_atom_ids(directory_name):
        """
        Infer the subjob and atom id's from an artifact directory name. This name should be of format:

        "artifact_SubjobId_AtomId"

        The method raises a ValueError if the directory_name does not match expected convention.

        :type directory_name: str
        :return: A tuple, with the first element being the subjob id, and the second element being the atom id.
        :rtype: (int, int)
        """
        id_match = re.search(r'artifact_(\d+)_(\d+)$', directory_name)

        if id_match is None:
            raise ValueError('Artifact directory {} did not meet naming convention'.format(directory_name))

        return int(id_match.group(1)), int(id_match.group(2))
