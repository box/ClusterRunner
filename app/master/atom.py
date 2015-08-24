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
    ):
        """
        :type command_string: str
        :type expected_time: float | None
        :type actual_time: float | None
        :type exit_code: int | None
        :type state: `:class:AtomState` | None
        """
        self.command_string = command_string
        self.expected_time = expected_time
        self.actual_time = actual_time
        self.exit_code = exit_code
        self.state = state
