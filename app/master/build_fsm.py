from enum import Enum
import time

from fysom import Fysom, FysomError
# WIP(joey): Fysom is not thread safe -- multiple threads could theoretically traverse
# WIP(joey): the same state transition simultaneously.

from app.util import log


class BuildState(str, Enum):
    """Posssible states for the FSM"""
    QUEUED = 'QUEUED'
    PREPARING = 'PREPARING'
    PREPARED = 'PREPARED'
    BUILDING = 'BUILDING'
    FINISHED = 'FINISHED'
    ERROR = 'ERROR'
    CANCELED = 'CANCELED'


class BuildEvent(str, Enum):
    """Events that correspond to FSM state transitions"""
    START_PREPARE = 'START_PREPARE'
    FINISH_PREPARE = 'FINISH_PREPARE'
    START_BUILDING = 'START_BUILDING'
    POSTBUILD_TASKS_COMPLETE = 'POSTBUILD_TASKS_COMPLETE'
    FAIL = 'FAIL'
    CANCEL = 'CANCEL'


class BuildFsm(object):
    """
                      +--------+
      (initial state) >>> | QUEUED |-----+
                          +--------+     |
                               |         |
                 START_PREPARE |         |                   CANCEL
                               v         |               START_PREPARE
                        +-----------+    |               FINISH_PREPARE
                        | PREPARING |----|                 +-------+
                        +-----------+    |                 |       |
                               |         |  CANCEL  +----------+   |
                FINISH_PREPARE |         |--------->| CANCELED |<--+
                               v         |          +----------+
                         +----------+    |                 |
                         | PREPARED |----|                 |
                         +----------+    |                 | FAIL
                               |   |     |                 v
                START_BUILDING |   |     |   FAIL   +---------+
                               v   |     |-----+--->|  ERROR  |<--+
                      +----------+ |     |     |    +---------+   |
                      | BUILDING |-(-----+     |          |       |
                      +----------+ |           |          +-------+
                               |   |           |             FAIL
      POSTBUILD_TASKS_COMPLETE |   |           |            CANCEL
                               v   v           |
                         +----------+          |
                     +-->| FINISHED |----------+
                     |   +----------+
                     |         |
                     +---------+
                        CANCEL
    """
    def __init__(self, build_id, enter_state_callbacks):
        """
        :type build_id: int
        :type enter_state_callbacks: dict[BuildState, callable]
        """
        self._logger = log.get_logger(__name__)
        self._build_id = build_id
        self._transition_timestamps = {state: None for state in BuildState}   # initialize all timestamps to None
        self._fsm = self._create_state_machine()

        for build_state, callback in enter_state_callbacks.items():
            self._register_enter_state_callback(build_state, callback)

    def _create_state_machine(self):
        """
        Create the Fysom object and set up transitions and states. Note that the first transition
        (none ==> initial) is triggered immediately on instantiation.
        :rtype: Fysom
        """
        return Fysom({
            'initial': BuildState.QUEUED,
            'events': [
                {'name': BuildEvent.START_PREPARE,
                 'src': BuildState.QUEUED,
                 'dst': BuildState.PREPARING},

                {'name': BuildEvent.FINISH_PREPARE,
                 'src': BuildState.PREPARING,
                 'dst': BuildState.PREPARED},

                {'name': BuildEvent.START_BUILDING,
                 'src': BuildState.PREPARED,
                 'dst': BuildState.BUILDING},

                {'name': BuildEvent.POSTBUILD_TASKS_COMPLETE,
                 'src': [
                     BuildState.PREPARED,
                     BuildState.BUILDING,
                 ],
                 'dst': BuildState.FINISHED},

                {'name': BuildEvent.CANCEL,
                 'src': [
                     BuildState.QUEUED,
                     BuildState.PREPARING,
                     BuildState.PREPARED,
                     BuildState.BUILDING,
                 ],
                 'dst': BuildState.CANCELED},

                {'name': BuildEvent.FAIL,
                 'src': '*',  # '*' means this transition can happen from any state.
                 'dst': BuildState.ERROR},

                # Cancellation immediately after request might cause this transition.
                {'name': BuildEvent.START_PREPARE,
                 'src': BuildState.CANCELED,
                 'dst': '='},  # '=' means the destination state is the same as the source state (no-op).

                # Cancellation during PREPARING will cause this transition.
                {'name': BuildEvent.FINISH_PREPARE,
                 'src': BuildState.CANCELED,
                 'dst': '='},

                # CANCEL is a no-op for a few states.
                {'name': BuildEvent.CANCEL,
                 'src': [
                     BuildState.CANCELED,
                     BuildState.ERROR,
                     BuildState.FINISHED,
                 ],
                 'dst': '='},
            ],
            'callbacks': {
                'onchangestate': self._record_state_timestamp,
            }
        })

    @property
    def state(self):
        """
        The current state of the state machine.
        :rtype: BuildState
        """
        return self._fsm.current

    @property
    def transition_timestamps(self):
        """
        Return a dict of BuildState to the timestamp that the state machine entered that state.
        :rtype: dict[BuildState, float|None]
        """
        return self._transition_timestamps.copy()  # return a copy to prevent external modification

    def trigger(self, build_event, __trigger_fail_on_error=True, **kwargs):
        """
        Trigger the specified event to make the state machine transition to a new state.

        :param build_event:
        :type build_event: BuildEvent
        :param __trigger_fail_on_error: Whether to make a recursive call in the case of failure -- this
            exists only for this method's internal use to prevent infinite recursion.
        :type __trigger_fail_on_error: bool
        :param kwargs: Parameters that will be attached to the event which is passed to callbacks
        :type kwargs: dict
        """
        try:
            self._fsm.trigger(build_event, **kwargs)

        except FysomError as ex:
            # Don't raise transition errors; just fail the build.
            self._logger.exception('Error during build state transition.')
            if __trigger_fail_on_error:
                error_msg = 'Error during build state transition. ({}: {})'.format(type(ex).__name__, ex)
                self.trigger(BuildEvent.FAIL, error_msg=error_msg, __trigger_fail_on_error=False)
            else:
                self._logger.critical('Build attempted to move to ERROR state but the transition itself failed!')

    def _register_enter_state_callback(self, build_state, callback):
        """
        Register a callback that will be executed by Fysom when the specified state is entered. This
        leverages Fysom magic which calls methods by name using a convention ("onenter<state_name>").

        :type build_state: BuildState
        :type callback: callable
        """
        setattr(self._fsm, 'onenter' + build_state, callback)

    def _record_state_timestamp(self, event):
        """
        Record a timestamp for a given build status. This is used to record the timing of the various
        build phases and is exposed via the Build object's API representation.
        """
        self._logger.debug('Build {} transitioned from {} to {}', self._build_id, event.src, event.dst)
        build_state = event.dst
        if self._transition_timestamps.get(build_state) is not None:
            self._logger.warning(
                'Overwriting timestamp for build {}, state {}'.format(self._build_id, build_state))
        self._transition_timestamps[build_state] = time.time()
