from enum import Enum


class AtomState(str, Enum):
    NOT_STARTED = 'NOT_STARTED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'


class Atom(object):
    def __init__(
            self,
            command_string,
            expected_time=None,
            actual_time=None,
            exit_code=None,
            state=None,
            atom_id=None,
            subjob_id=None
    ):
        """
        :type command_string: str
        :type expected_time: float | None
        :type actual_time: float | None
        :type exit_code: int | None
        :type state: `:class:AtomState` | None
        :type atom_id: int | None
        :type subjob_id: int | None
        """
        self.command_string = command_string
        self.expected_time = expected_time
        self.actual_time = actual_time
        self.exit_code = exit_code
        self.state = state
        self.subjob_id = subjob_id
        self.id = atom_id

    def api_representation(self):
        return {
            'command_string': self.command_string,
            'expected_time': self.expected_time,
            'actual_time': self.actual_time,
            'exit_code': self.exit_code,
            'state': self.state,
            'id': self.id,
            'subjob_id': self.subjob_id,
        }
