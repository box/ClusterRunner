from unittest.mock import mock_open

import collections
import json
from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.event_log import EventLog, LOG_CACHE_EXPIRE_TIME_IN_HOURS


class TestEventLog(BaseUnitTestCase):

    _FAKE_EVENTLOG_CONTENTS = '''
{"__id__": 1, "__tag__": "SERVICE_STARTED", "__timestamp__": 1410902723.979315}
{"__id__": 2, "__tag__": "NETWORK_REQUEST_RECEIVED", "__timestamp__": 1410902724.0863}
{"__id__": 3, "__tag__": "NETWORK_REQUEST_RECEIVED", "__timestamp__": 1410902729.896991}
    '''

    def test_get_events_should_return_all_events_when_no_params_specified(self):
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.event_log.open', new=open_mock, create=True)
        event_log = EventLog(filename='my_fake_eventlog.log')

        events = event_log.get_events()
        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [1, 2, 3],
                             'get_events() with no params should return all events '
                             'as ordered in eventlog file')

    def test_get_events_should_return_all_events_when_no_params_specified_with_cache(self):
        event_log = EventLog(filename='my_fake_eventlog.log')
        cache_events = [json.loads(line)
                        for line in self._FAKE_EVENTLOG_CONTENTS.strip().splitlines()]
        event_log._log_cache = cache_events
        events = event_log.get_events()
        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [1, 2, 3],
                             'get_events() with no params should return all events '
                             'as ordered in the cache')

    def test_get_events_should_return_all_events_since_a_specified_timestamp(self):
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.event_log.open', new=open_mock, create=True)
        event_log = EventLog(filename='my_fake_eventlog.log')

        since_timestamp = 1410902723.979315  # timestamp of the first event
        events = event_log.get_events(since_timestamp=since_timestamp)
        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [2, 3],
                             'get_events() with since_timestamp param should return '
                             'all events since specified timestamp')

    def test_get_events_should_return_all_events_since_a_specified_event_id(self):
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.event_log.open', new=open_mock, create=True)
        event_log = EventLog(filename='my_fake_eventlog.log')

        since_id = 2 # id of second event
        events = event_log.get_events(since_id=since_id)

        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [3],
                             'get_events() with since_id should return all events '
                             'since an id')

    def test_get_events_raises_exception_if_both_timestamp_and_id_are_specified(self):
        event_log = EventLog(filename='my_fake_eventlog.log')

        with self.assertRaises(ValueError,
                               msg='get_events() should raise erro if both id and timestamp '
                                   'are specified'):
            event_log.get_events(since_timestamp=0.0, since_id=0)

    def test_get_events_should_return_events_from_file_if_timestamp_not_in_range(self):
        log_lines = self._FAKE_EVENTLOG_CONTENTS.strip().splitlines()
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.event_log.open', new=open_mock, create=True)
        event_log = EventLog(filename='my_fake_eventlog.log')
        event_log._log_cache = [json.loads(line) for line in log_lines[2:]]

        since_timestamp = 1410902723.979315  # timestamp of the first event
        events = event_log.get_events(since_timestamp=since_timestamp)
        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [2, 3],
                             'get_events() with since_timestamp param should return '
                             'all events since specified timestamp')

    def test_get_events_should_write_to_cache(self):
        self.patch('app.util.event_log.TaggingLogger')
        event_log = EventLog(filename='my_fake_eventlog.log')
        event_log.record_event('my_tag', message='foo')
        event = event_log._log_cache[0]
        self.assertEqual(event['message'], 'foo')

    def test_oldest_cache_event_is_stale_should_be_true_if_event_timestamp_is_greater_than_expire_time(self):
        event_log = EventLog(filename='my_fake_eventlog.log')
        cache_events = [json.loads(line)
                        for line in self._FAKE_EVENTLOG_CONTENTS.strip().splitlines()]
        event_log._log_cache = cache_events
        events = event_log.get_events()
        # set the new time to 1 second past the expiration time
        new_timestamp = event_log._log_cache[0]['__timestamp__'] + LOG_CACHE_EXPIRE_TIME_IN_HOURS * 60 * 60 + 1
        new_event = {'__id__': 4, '__tag__': 'NETWORK_REQUEST_RECEIVED', '__timestamp__': new_timestamp}
        event_log._log_cache.append(new_event)
        self.assertTrue(event_log._oldest_cache_event_is_stale())

    def test_oldest_cache_event_is_stale_should_be_false_if_event_timestamp_is_less_than_expire_time(self):
        event_log = EventLog(filename='my_fake_eventlog.log')
        cache_events = [json.loads(line)
                        for line in self._FAKE_EVENTLOG_CONTENTS.strip().splitlines()]
        event_log._log_cache = cache_events
        # set the new time to 1 second past the expiration time
        new_timestamp = event_log._log_cache[0]['__timestamp__'] + 45
        time_mock = self.patch('app.util.event_log.time')
        time_mock.time.return_value = new_timestamp
        self.assertFalse(event_log._oldest_cache_event_is_stale())


