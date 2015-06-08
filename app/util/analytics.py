from app.util.event_log import EventLog
from app.util.exceptions import ItemNotReadyError

BUILD_REQUEST_QUEUED = 'BUILD_REQUEST_QUEUED'
BUILD_PREPARE_START = 'BUILD_PREPARE_START'
BUILD_PREPARE_FINISH = 'BUILD_PREPARE_FINISH'
BUILD_SETUP_START = 'BUILD_SETUP_START'
BUILD_SETUP_FINISH = 'BUILD_SETUP_FINISH'
MASTER_RECEIVED_RESULT = 'MASTER_RECEIVED_RESULT'
MASTER_TRIGGERED_SUBJOB = 'MASTER_TRIGGERED_SUBJOB'
SERVICE_STARTED = 'SERVICE_STARTED'
SUBJOB_EXECUTION_FINISH = 'SUBJOB_EXECUTION_FINISH'
SUBJOB_EXECUTION_START = 'SUBJOB_EXECUTION_START'
ATOM_START = 'ATOM_START'
ATOM_FINISH = 'ATOM_FINISH'

_event_log = None


def initialize(eventlog_file=None):
    """
    Initialize the analytics output. This will cause analytics events to be output to either a file or stdout.

    If this function is not called, analytics events will not be output. If it is called with a filename, the events
    will be output to that file. If it is called with 'STDOUT' or None, the events will be output to stdout.

    :param eventlog_file: The filename to output events to, 'STDOUT' to output to stdout, None to disable event logging
    :type eventlog_file: str | None
    """
    global _event_log

    _event_log = EventLog(filename=eventlog_file)


def record_event(tag, log_msg=None, **event_data):
    """
    Record an event containing the specified data. Currently this just json-ifies the event and outputs it to the
    configured analytics logger (see analytics.initialize()).

    :param tag: A string identifier that describes the event being logged (e.g., "REQUEST_SENT")
    :type tag: str
    :param log_msg: A message that will also be logged to the human-readable log (not the event log). It will be string
        formatted with the event_data dict. This is a convenience for logging to both human- and machine-readable logs.
    :type log_msg: str
    :param event_data: Free-form key value pairs that make up the event
    :type event_data: dict
    """
    if _event_log:
        _event_log.record_event(tag, log_msg=log_msg, **event_data)


def get_events(since_timestamp=None, since_id=None):
    """
    Retrieve all events from the current eventlog since the given timestamp or event id. This is used to expose events
    via the API and is useful for building dashboards that monitor the system.

    :param since_timestamp: Get all events after (greater than) this timestamp
    :type since_timestamp: float | None
    :param since_id: Get all events after (greater than) this id
    :type since_id: int | None
    :return: The list of events in the given range
    :rtype: list[dict] | None
    """
    if _event_log:
        since_timestamp = float(since_timestamp) if since_timestamp else since_timestamp
        since_id = int(since_id) if since_id else since_id
        return _event_log.get_events(since_timestamp=since_timestamp, since_id=since_id)
    else:
        raise ItemNotReadyError('Analytics was not initialized. Call initialize first')
