import collections
import json
from logbook import RotatingFileHandler, StreamHandler
from logbook.more import TaggingHandler, TaggingLogger
import os
import sys
import time

from app.util import fs, log
from app.util.conf.configuration import Configuration
from app.util.counter import Counter


BUILD_REQUEST_QUEUED = 'BUILD_REQUEST_QUEUED'
BUILD_PREPARE_START = 'BUILD_PREPARE_START'
BUILD_PREPARE_FINISH = 'BUILD_PREPARE_FINISH'
MASTER_RECEIVED_RESULT = 'MASTER_RECEIVED_RESULT'
MASTER_TRIGGERED_SUBJOB = 'MASTER_TRIGGERED_SUBJOB'
SERVICE_STARTED = 'SERVICE_STARTED'
SUBJOB_EXECUTION_FINISH = 'SUBJOB_EXECUTION_FINISH'
SUBJOB_EXECUTION_START = 'SUBJOB_EXECUTION_START'

_analytics_logger = None
_eventlog_file = None
_event_id_generator = Counter()


def initialize(eventlog_file=None):
    """
    Initialize the analytics output. This will cause analytics events to be output to either a file or stdout.

    If this function is not called, analytics events will not be output. If it is called with a filename, the events
    will be output to that file. If it is called with 'STDOUT' or None, the events will be output to stdout.

    :param eventlog_file: The filename to output events to, 'STDOUT' to output to stdout, None to disable event logging
    :type eventlog_file: str | None
    """
    global _analytics_logger, _eventlog_file

    _eventlog_file = eventlog_file
    if not eventlog_file:
        _analytics_logger = None
        return

    if eventlog_file.upper() == 'STDOUT':
        event_handler = StreamHandler(sys.stdout)
    else:
        fs.create_dir(os.path.dirname(eventlog_file))
        previous_log_file_exists = os.path.exists(eventlog_file)

        event_handler = RotatingFileHandler(
            filename=eventlog_file,
            max_size=Configuration['max_eventlog_file_size'],
            backup_count=Configuration['max_eventlog_file_backups'],
        )
        if previous_log_file_exists:
            event_handler.perform_rollover()  # force starting a new eventlog file on application startup

    event_handler.format_string = '{record.message}'  # only output raw log message -- no timestamp or log level
    handler = TaggingHandler(
        {'event': event_handler},  # enable logging to the event_handler with the event() method
        bubble=True,
    )
    handler.push_application()

    _analytics_logger = TaggingLogger('analytics', ['event'])


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
    if _analytics_logger:
        event_data['__id__'] = _event_id_generator.increment()
        event_data['__tag__'] = tag
        event_data['__timestamp__'] = time.time()
        _analytics_logger.event(json.dumps(event_data, sort_keys=True))  # pylint: disable=no-member
        # todo(joey): cache most recent N events so get_events() doesn't always have to load file

    if log_msg:
        logger = log.get_logger(__name__)
        logger.info(log_msg, **event_data)


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
    # eventlogs to STDOUT should only be used in debug situations, so don't worry about making events available.
    if _eventlog_file is None or _eventlog_file.upper() == 'STDOUT':
        return None

    if None not in (since_timestamp, since_id):
        raise ValueError('Invalid arguments: only one of "since_timestamp" and "since_id" can be specified.')

    # set defaults here instead of in function def so we don't have to worry about defaults in the web layer.
    since_timestamp = float(since_timestamp) if since_timestamp else 0.0
    since_id = int(since_id) if since_id else 0

    with open(_eventlog_file, 'r') as f:
        # todo(joey): This is inefficient since it reads the whole log file into memory (can be several megabytes).
        # We probably want something like http://code.activestate.com/recipes/120686/
        reversed_log_lines = reversed(f.readlines())

    returned_events = []
    for log_line in reversed_log_lines:
        try:
            event = json.loads(log_line, object_pairs_hook=collections.OrderedDict)  # OrderedDict keeps keys sorted
        except ValueError:
            continue  # skip this line if it's invalid json

        event_timestamp = event.get('__timestamp__')
        event_id = event.get('__id__')

        if event_timestamp > since_timestamp and event_id != since_id:
            returned_events.append(event)  # this event is in the requested range so we add it to the response
        else:
            break  # we've gone past the start of the range so we're done

    return list(reversed(returned_events))  # events were added from latest to earliest; reverse to get correct order
