import os

from app.util.conf.configuration import Configuration
from app.util.log import get_logger


class Subjob(object):
    ATOM_DIR_FORMAT = "artifact_{}_{}"
    OUTPUT_FILE = 'clusterrunner_console_output'
    EXIT_CODE_FILE = 'clusterrunner_exit_code'
    COMMAND_FILE = 'clusterrunner_command'
    TIMING_FILE = 'clusterrunner_time'

    def __init__(self, build_id, subjob_id, project_type, job_config, atoms):
        """
        :param build_id:
        :type build_id: int
        :param subjob_id:
        :type subjob_id: int
        :param project_type:
        :type project_type: ProjectType
        :param job_config: the job's configuration from cluster_runner.yaml
        :type job_config: JobConfig
        :param atoms: the atom project_type strings
        :type atoms: list[Atom]
        :return:
        """
        self._logger = get_logger(__name__)
        self._build_id = build_id
        self._subjob_id = subjob_id
        self.project_type = project_type
        self.job_config = job_config
        self._atoms = atoms
        self.timings = {}  # a dict, atom_ids are the keys and seconds are the values

    def api_representation(self):
        """
        :rtype: dict [str, str]
        """
        return {
            'id': self._subjob_id,
            'command': self.job_config.command,
            'atoms': self.get_atoms()
        }

    def get_atoms(self):
        return [{
            'id': idx,
            'atom': atom.command_string,
            'expected_time': atom.expected_time,
            'actual_time': atom.actual_time,
        } for idx, atom in enumerate(self._atoms)]

    def build_id(self):
        """
        :return:
        :rtype: int
        """
        return self._build_id

    def subjob_id(self):
        """
        :return:
        :rtype: int
        """
        return self._subjob_id

    def atomic_commands(self):
        """
        The list of atom commands -- the atom id for each atom is implicitly defined by the index of the list.
        :rtype: list[str]
        """
        job_command = self.job_config.command
        return ['{} {}'.format(atom.command_string, job_command) for atom in self._atoms]

    def _timings_file_path(self, atom_id, result_root=None):
        """
        The path to read/write the subjob's timing data from, relative to a root 'result' directory

        :param int atom_id: id for the atom
        :param str result_root: root of the result path
        :rtype: str
        """
        return os.path.join(self.artifact_dir(result_root),
                            Subjob.ATOM_DIR_FORMAT.format(self._subjob_id, atom_id),
                            Subjob.TIMING_FILE)

    def add_timings(self, timings):
        """
        Add timing data for this subjob's atoms, collected from a slave
        :param timings:
        :type timings: dict [string, float]
        """
        self.timings.update(timings)

    def read_timings(self):
        """
        The timing data for each atom should be stored in the atom directory.  Parse them, associate
        them with their atoms, and return them.
        :rtype: dict [str, float]
        """
        timings = {}
        for atom_id, atom in enumerate(self._atoms):

            timings_file_path = self._timings_file_path(
                atom_id, result_root=Configuration['results_directory'])
            if os.path.exists(timings_file_path):
                with open(timings_file_path, 'r') as f:
                    # Strip out the project directory from atom timing data in order to have all
                    # atom timing data be relative and project directory agnostic (the project
                    # directory will be a generated unique path for every build).
                    atom_key = atom.command_string.replace(self.project_type.project_directory, '')
                    atom_time = float(f.readline())
                    timings[atom_key] = atom.actual_time = atom_time
            else:
                self._logger.warning('No timing data for subjob {} atom {}.',
                                     self._subjob_id, atom_id)

        if len(timings) == 0:
            self._logger.warning('No timing data for subjob {}.', self._subjob_id)

        return timings

    def artifact_dir(self, result_root=None):
        """
        Generate the path to where the artifacts for a subjob should be stored on the file system.

        :type result_root: str
        :rtype: string
        """
        return os.path.join(
            result_root or Configuration['artifact_directory'],
            str(self._build_id)
        )
