from app.master.atom import Atom
from app.util import log
from app.util.process_utils import get_environment_variable_setter_command


class Atomizer(object):
    """
    An Atomizer takes care of translating the commands as parsed from the "atomizers" section of the project config
    into a list of atoms. The actual computed atoms are just environment variable export shell commands that are then
    prepended to whatever commands were specified in the "commands" section of the project config.
    """
    def __init__(self, atomizer_dicts):
        """
        :param atomizer_dicts: A list of dicts mapping atomizer env var names to atomizer commands
        :type atomizer_dicts: list[dict[str, str]]
        """
        self._logger = log.get_logger(__name__)
        self._atomizer_dicts = atomizer_dicts

    def atomize_in_project(self, project_type):
        """
        Translate the atomizer dicts that this instance was initialized with into a list of actual atom commands. This
        executes atomizer commands inside the given project in order to generate the atoms.

        :param project_type: The ProjectType instance in which to execute the atomizer commands
        :type project_type: ProjectType
        :return: The list of environment variable "export" atom commands
        :rtype: list[app.master.atom.Atom]
        """
        atoms_list = []
        for atomizer_dict in self._atomizer_dicts:
            for atomizer_var_name, atomizer_command in atomizer_dict.items():
                atomizer_output, exit_code = project_type.execute_command_in_project(atomizer_command)
                if exit_code != 0:
                    self._logger.error('Atomizer command "{}" for variable "{}" failed with exit code: {} and output:'
                                       '\n{}', atomizer_command, atomizer_var_name, exit_code, atomizer_output)
                    raise AtomizerError('Atomizer command failed!')

                new_atoms = []
                for atom_value in atomizer_output.strip().splitlines():
                    # For purposes of matching atom string values across builds, we must replace the generated/unique
                    # project directory with its corresponding universal environment variable: '$PROJECT_DIR'.
                    atom_value = atom_value.replace(project_type.project_directory, '$PROJECT_DIR')
                    new_atoms.append(Atom(get_environment_variable_setter_command(atomizer_var_name, atom_value)))
                atoms_list.extend(new_atoms)

        return atoms_list


class AtomizerError(Exception):
    """
    Represents an error during atomization.
    """
