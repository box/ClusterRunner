import os

from app.master.atom import AtomState
from app.master.build_artifact import BuildArtifact
from app.util.conf.configuration import Configuration
from app.util.log import get_logger


class Subjob(object):
    def __init__(self, build_id, subjob_id, project_type, job_config, atoms):
        """
        :param build_id:
        :type build_id: int
        :param subjob_id:
        :type subjob_id: int
        :param project_type:
        :type project_type: ProjectType
        :param job_config: the job's configuration from clusterrunner.yaml
        :type job_config: JobConfig
        :param atoms: the atom project_type strings
        :type atoms: list[app.master.atom.Atom]
        :return:
        """
        self._logger = get_logger(__name__)
        self._build_id = build_id
        self._subjob_id = subjob_id
        self.project_type = project_type
        self.job_config = job_config
        self._atoms = atoms
        self._set_atoms_subjob_id(atoms, subjob_id)
        self._set_atom_state(AtomState.NOT_STARTED)
        self.timings = {}  # a dict, atom_ids are the keys and seconds are the values
        self.slave = None  # The slave that had been assigned this subjob. Is None if not started.

    def _set_atoms_subjob_id(self, atoms, subjob_id):
        """
        Set the subjob_id on each atom
        :param atoms: an array of atoms to set the subjob_id on
        :type atoms: list[app.master.atom.Atom]
        :param subjob_id: the subjob_id to set on the atoms
        :type subjob_id: int
        """
        for atom in atoms:
            atom.subjob_id = subjob_id

    def _set_atom_state(self, state):
        """
        Set the state of all atoms of the subjob.

        :param state: up-to-date state of all atoms of the subjob
        :type state: `:class:AtomState`
        """
        for atom in self._atoms:
            atom.state = state

    def mark_in_progress(self, slave):
        """
        Mark the subjob IN_PROGRESS, which marks the state of all the atoms of the subjob IN_PROGRESS.

        :param slave: the slave node that has been assigned this subjob.
        :type slave: Slave
        """
        self._set_atom_state(AtomState.IN_PROGRESS)
        self.slave = slave

    def mark_completed(self):
        """
        Mark the subjob COMPLETED, which marks the state of all the atoms of the subjob COMPLETED.
        """
        self._set_atom_state(AtomState.COMPLETED)

    def api_representation(self):
        """
        :rtype: dict [str, str]
        """

        return {
            'id': self._subjob_id,
            'command': self.job_config.command,
            'atoms': [atom.api_representation() for atom in self._atoms],
            'slave': self.slave.url if self.slave else None,
        }

    @property
    def atoms(self):
        """
        :rtype: list[app.master.atom.Atom]
        """
        return self._atoms

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
            artifact_dir = BuildArtifact.atom_artifact_directory(
                self.build_id(),
                self.subjob_id(),
                atom_id,
                result_root=Configuration['results_directory']
            )
            timings_file_path = os.path.join(artifact_dir, BuildArtifact.TIMING_FILE)
            if os.path.exists(timings_file_path):
                with open(timings_file_path, 'r') as f:
                    atom.actual_time = float(f.readline())
                    timings[atom.command_string] = atom.actual_time
            else:
                self._logger.warning('No timing data for subjob {} atom {}.',
                                     self._subjob_id, atom_id)

        if len(timings) == 0:
            self._logger.warning('No timing data for subjob {}.', self._subjob_id)

        return timings
