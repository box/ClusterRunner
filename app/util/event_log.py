import collections
import json
import os
import sys
import time

from logbook import RotatingFileHandler, StreamHandler
from logbook.more import TaggingHandler, TaggingLogger

from app.util import fs, log
from app.util.conf.configuration import Configuration
from app.util.counter import Counter

LOG_CACHE_EXPIRE_TIME_IN_HOURS = 5
LOG_CACHE_THRESHOLD = 100000


class EventLog:
    def __init__(self, filename=None):
        """
        :param filename: The name of the logfile
        :type filename: str | None
        """
        self.filename = filename
        self.logging_disabled = filename is None
        self._analytics_logger = None
        self._event_id_generator = Counter()
        self._log_cache = collections.deque()
        self._logger = log.get_logger(__name__)

    def _initialize(self):
        """
        Initialize logging construct
        """
        if not self.logging_disabled:
            self._initialize_event_handler()
            self._analytics_logger = self._initialize_analytics_logger()

    def _initialize_event_handler(self):
        # only output raw log message -- no timestamp or log level
        event_handler = self._get_event_handler()
        event_handler.format_string = '{record.message}'
        handler = TaggingHandler(
            {'event': event_handler},
            bubble=True,
        )
        handler.push_application()

    def _initialize_analytics_logger(self):
        """
        Initializes the analytics
        """
        return TaggingLogger('analytics', ['event'])

    def _get_event_handler(self):
        """
        Retrieves the correct event handler. Returns a Stream Handler
        if the event should write to STDOUT, otherwise it will return
        a ready RotatingFileHandler.

        Both subclasses inherit from the StreamHandler base class.

        :return: Event handler
        :rtype: StreamHandler
        """
        if self.filename.upper() == 'STDOUT':
            return StreamHandler(sys.stdout)
        else:
            fs.create_dir(os.path.dirname(self.filename))
            previous_log_file_exists = os.path.exists(self.filename)

            event_handler = RotatingFileHandler(
                filename=self.filename,
                max_size=Configuration['max_eventlog_file_fize'],
                backup_count=Configuration['max_eventlog_file_backups']
            )
            if previous_log_file_exists:
                event_handler.perform_rollover()  # force starting a new eventlog file on application startup

            return event_handler

    def _generate_event_id(self):
        """
        :rtype: int
        """
        return self._event_id_generator.increment()

    def record_event(self, tag, log_msg=None, **event_data):
        """
        Record an event containing the specified data. Currently this just json-ifies the event and outputs it to
        the configured analytics logger (see analytics.initialize()).

        :param tag: A string identifier that describes the event being logged (e.g., "REQUEST_SENT")
        :type tag: str
        :param log_msg: A message that will also be logged to the human-readable log (not the event log). It will be
            string formatted with the event_data dict.  This is a convenience for logging to both human- and
            machine-readable logs.
        :type log_msg: str
        :param event_data: Free-form key value pairs that make up the event
        :type event_data: dict
        """
        if not self.logging_disabled:
            event_data['__id__'] = self._generate_event_id()
            event_data['__tag__'] = tag
            event_data['__timestamp__'] = time.time()
            json_dumps = json.dumps(event_data, sort_keys=True)
            self._write_to_analytics_logger(json_dumps)
            self._write_to_log_cache(event_data)

        if log_msg:
            self._logger.info(log_msg, **event_data)

    def _write_to_analytics_logger(self, json_dumps):
        """
        :param json_dumps: A json encoded message that describes the event being logged
        :type json_dumps: str
        """
        if self._analytics_logger:
            self._analytics_logger.event(json_dumps)  # pylint: disable=no-member

    def _write_to_log_cache(self, event_data):
        """
        :param event_data: Free-form key value pairs that make up the event
        :type event_data: dict
        """
        self._log_cache.append(event_data)
        self._expire_stale_items_in_cache()

    def _expire_stale_items_in_cache(self):
        """
        Expires stale items in the cache. An item in the cache is considered stale if the timestamp is
        significantly older than the current time. This expiration time is determined by the constant,
        LOG_CACHE_EXPIRE_TIME_IN_HOURS.

        Since we do not want to artificially impose limits on the log cache, we will not expire items
        if the total length of the log cache is less than LOG_CACHE_THRESHOLD.
        """
        while len(self._log_cache) > LOG_CACHE_THRESHOLD and self._oldest_cache_event_is_stale():
            self._log_cache.popleft()

    def _oldest_cache_event_is_stale(self):
        """
        Returns whether the time stamp of the oldest event is stale in comparison with the current time.
        The time is considered stale if it is is older than oldest time + LOG_CACHE_EXPIRE_TIME_IN_HOURS

        :rtype: bool
        """
        try:
            oldest = self._oldest_timestamp_in_cache()
            return oldest + LOG_CACHE_EXPIRE_TIME_IN_HOURS * 60 * 60 < time.time()
        except TypeError:
            return False

    def _oldest_timestamp_in_cache(self):
        """
        :rtype: float | None
        """
        if len(self._log_cache) == 0:
            return None
        else:
            return self._log_cache[0]['__timestamp__']

    def _oldest_id_in_cache(self):
        if len(self._log_cache) == 0:
            return None
        else:
            return self._log_cache[0]['__id__']

    def get_events(self, since_timestamp=None, since_id=None):
        """
        Retrieve all events from the current eventlog since the given timestamp or event id.
        This is used to expose events via the API and is useful for building dashboards
        that monitor the system.

        :param since_timestamp: Get all events after (greater than) this timestamp
        :type since_timestamp: float | None
        :param since_id:  Get all events after (greater than) this id.
        :type since_id: int | None
        :return: The list of events in the given range
        :rtype: list[dict] | None
        """
        if self.logging_disabled or self.filename.upper() == 'STDOUT':
            return None

        if since_timestamp is not None and since_id is not None:
            raise ValueError('since_timestamp and since_id can not be used at the same time')
        if self._should_try_get_event_from_log_cache(since_id=since_id, since_timestamp=since_timestamp):
            # use the events from cache, but failover to fetch from the file
            return self._get_events_from_reversed_generator(
                generator=self._reversed_log_cache_event_generator(),
                since_timestamp=since_timestamp,
                since_id=since_id
            )
        else:
            return self._get_events_from_reversed_generator(
                generator=self._reversed_log_file_event_generator(),
                since_timestamp=since_timestamp,
                since_id=since_id
            )

    def _should_try_get_event_from_log_cache(self, since_id=None,
                                             since_timestamp=None):
        if len(self._log_cache) == 0:
            return False
        else:
            has_timestamp = since_timestamp is None or since_timestamp >= self._oldest_timestamp_in_cache()
            has_id = since_id is None or since_id > self._oldest_id_in_cache()

            return has_timestamp and has_id

    def _get_events_from_reversed_generator(self, generator=None, since_timestamp=None,
                                            since_id=None):
        """
        :param generator:
        :param since_timestamp:
        :param since_id:
        :return:
        :rtype: list[dict]
        """
        generator = generator or self._reversed_log_cache_event_generator()
        returned_events = []
        for event in generator:
            event_timestamp = event.get('__timestamp__')
            event_id = event.get('__id__')
            if since_timestamp and event_timestamp <= since_timestamp or \
               since_id and event_id == since_id:
                break
            else:
                returned_events.append(event)

        return list(reversed(returned_events))

    def _reversed_log_cache_event_generator(self):
        # what's the return type of a generator?
        reversed_events = reversed(self._log_cache)
        for event in reversed_events:
            yield event

    def _reversed_log_file_event_generator(self):
        # todo: this is inefficient since it reads the entire file backwards,
        # maybe read it backwards in blocks like this http://code.activestate.com/recipes/120686/
        with open(self.filename, 'r') as f:
            log_lines_from_file = f.readlines()
            reversed_log_lines = reversed(log_lines_from_file)
            for log_line in reversed_log_lines:
                try:
                    event = json.loads(log_line, object_pairs_hook=collections.OrderedDict)
                    yield event
                except ValueError:
                    continue
