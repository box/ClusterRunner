from enum import Enum

from app.util.process_utils import get_environment_variable_setter_command


class AtomState(str, Enum):
    NOT_STARTED = 'NOT_STARTED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'


class Atom(object):
    def __init__(
            self,
            env_var_name,
            atom_value,
            expected_time=None,
            actual_time=None,
            exit_code=None,
            state=None,
    ):
        """
        :type env_var_name: str
        :type atom_value: str
        :type expected_time: float | None
        :type actual_time: float | None
        :type exit_code: int | None
        :type state: `:class:AtomState` | None
        """
        self._env_var_name = env_var_name
        self.atom_value = atom_value
        self.expected_time = expected_time
        self.actual_time = actual_time
        self.exit_code = exit_code
        self.state = state

        # Convert atomizer command output into environment variable export commands.
        self.command_string = get_environment_variable_setter_command(self._env_var_name, self.atom_value)
