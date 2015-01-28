from unittest.mock import mock_open

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util import analytics


class TestAnalytics(BaseUnitTestCase):

    _FAKE_EVENTLOG_CONTENTS = '''
{"__id__": 1, "__tag__": "SERVICE_STARTED", "__timestamp__": 1410902723.979315}
{"__id__": 2, "__tag__": "NETWORK_REQUEST_RECEIVED", "__timestamp__": 1410902724.0863}
{"__id__": 3, "__tag__": "NETWORK_REQUEST_RECEIVED", "__timestamp__": 1410902729.896991}
    '''

    def test_get_events_returns_all_events_with_no_params_specified(self):
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.analytics.open', new=open_mock, create=True)
        self.patch('app.util.analytics._eventlog_file', new='my_fake_eventlog.log')

        events = analytics.get_events()

        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [1, 2, 3],
                             'get_events() with no params should return all events as ordered in eventlog file.')

    def test_get_events_returns_all_events_since_a_specified_timestamp(self):
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.analytics.open', new=open_mock, create=True)
        self.patch('app.util.analytics._eventlog_file', new='my_fake_eventlog.log')

        since_timestamp = 1410902723.979315  # timestamp of the first event
        events = analytics.get_events(since_timestamp=since_timestamp)

        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [2, 3],
                             'get_events() with no params should return all events since the specified timestamp.')

    def test_get_events_returns_all_events_since_a_specified_event_id(self):
        open_mock = mock_open(read_data=self._FAKE_EVENTLOG_CONTENTS)
        self.patch('app.util.analytics.open', new=open_mock, create=True)
        self.patch('app.util.analytics._eventlog_file', new='my_fake_eventlog.log')

        since_id = 2  # id of second event
        events = analytics.get_events(since_id=since_id)

        returned_event_ids = [event['__id__'] for event in events]
        self.assertListEqual(returned_event_ids, [3],
                             'get_events() with no params should return all events since the specified id.')

    def test_get_events_raises_exception_if_both_timestamp_and_id_are_specified(self):
        self.patch('app.util.analytics._eventlog_file', new='my_fake_eventlog.log')

        with self.assertRaises(ValueError, msg='get_events() should raise if both timestamp and id are specified.'):
            analytics.get_events(since_timestamp=0.0, since_id=0)

    def test_get_events_returns_none_when_no_initialization_performed(self):
        events = analytics.get_events()
        self.assertEqual(events, None, 'get_events() should return None if no initialization was done.')

    def test_record_event_with_log_msg_logs_correct_message(self):
        analytics.record_event(
            'SOME_EVENT_TAG',
            log_msg='Build {build_id} was looking pretty {build_adjective}!',
            build_id=12,
            build_adjective='freaky')

        self.assertTrue(
            self.log_handler.has_info('Build 12 was looking pretty freaky!'),
            'Passing a log_msg param to record_event() should log an info-level message to the application log.')
