from app.util import log


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
        :rtype: list[Atom]
        """
        atoms_list = []
        for atomizer_dict in self._atomizer_dicts:
            for atomizer_var_name, atomizer_command in atomizer_dict.items():
                atomizer_output, exit_code = project_type.execute_command_in_project(atomizer_command)
                if exit_code != 0:
                    self._logger.error('Atomizer command "{}" for variable "{}" failed with exit code: {} and output:'
                                       '\n{}', atomizer_command, atomizer_var_name, exit_code, atomizer_output)
                    raise AtomizerError('Atomizer command failed!')

                # Convert atomizer command output into environment variable export commands.
                new_atoms = [Atom('export {}="{}";'.format(atomizer_var_name, atom_value))
                             for atom_value in atomizer_output.strip().splitlines()]
                atoms_list.extend(new_atoms)

        return atoms_list


class Atom(object):
    def __init__(self, command_string, expected_time=None, actual_time=None):
        """
        :type command_string: str
        :type expected_time: float
        :type actual_time: float
        """
        self.command_string = command_string
        self.expected_time = expected_time
        self.actual_time = actual_time


class AtomizerError(Exception):
    """
    Represents an error during atomization.
    """
