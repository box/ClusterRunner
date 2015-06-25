from app.util.process_utils import get_environment_variable_setter_command


class Atom(object):
    def __init__(self, env_var_name, atom_value, expected_time=None, actual_time=None):
        """
        :type env_var_name: str
        :type atom_value: str
        :type expected_time: float
        :type actual_time: float
        """
        self._env_var_name = env_var_name
        self._atom_value = atom_value
        self.expected_time = expected_time
        self.actual_time = actual_time

        # Convert atomizer command output into environment variable export commands.
        self.command_string = get_environment_variable_setter_command(self._env_var_name, self._atom_value)
