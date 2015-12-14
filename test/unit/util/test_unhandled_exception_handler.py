from contextlib import suppress
import sys
from threading import Thread
from unittest.mock import call, mock_open, MagicMock

from app.util import process_utils
from test.framework.base_unit_test_case import BaseUnitTestCase
from test.framework.comparators import AnyStringMatching
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class TestUnhandledExceptionHandler(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.exception_handler = UnhandledExceptionHandler.singleton()

    def test_handler_logs_caught_exceptions_and_calls_teardown_callbacks(self):
        callbacks = [MagicMock(), MagicMock(), MagicMock()]
        for arg_i, callback in enumerate(callbacks):
            self.exception_handler.add_teardown_callback(callback, arg_i)

        with suppress(SystemExit):
            with self.exception_handler:
                raise Exception

        for arg_i, callback in enumerate(callbacks):
            callback.assert_called_once_with(arg_i)  # Each callback should be executed once with the correct args.
        exception_was_logged = self.log_handler.has_error('Unhandled exception handler caught exception.')
        self.assertTrue(exception_was_logged, 'Exception handler should log exceptions.')

    def test_handles_platform_does_not_support_SIGINFO(self):
        UnhandledExceptionHandler.reset_singleton()
        mock_signal = self.patch('app.util.unhandled_exception_handler.signal')

        def register_signal_handler(sig, _):
            if sig == process_utils.SIGINFO:
                raise ValueError
        mock_signal.signal.side_effect = register_signal_handler
        UnhandledExceptionHandler.singleton()

    def test_exceptions_in_teardown_callbacks_are_caught_and_logged(self):
        an_evil_callback = MagicMock(side_effect=Exception)
        self.exception_handler.add_teardown_callback(an_evil_callback)

        with suppress(SystemExit):
            with self.exception_handler:
                raise Exception

        self.assertEqual(an_evil_callback.call_count, 1, 'A teardown callback should be executed once.')
        callback_exception_was_logged = self.log_handler.has_error(
            AnyStringMatching('Exception raised by teardown callback.*')
        )
        self.assertTrue(callback_exception_was_logged, 'Exception handler should log teardown callback exceptions.')

    def test_exceptions_in_teardown_callbacks_do_not_prevent_other_callbacks(self):
        callbacks = [MagicMock(side_effect=Exception),
                     MagicMock(side_effect=Exception),
                     MagicMock(side_effect=Exception)]
        for callback in callbacks:
            self.exception_handler.add_teardown_callback(callback)

        with suppress(SystemExit):
            with self.exception_handler:
                raise Exception

        for callback in callbacks:
            self.assertEqual(callback.call_count, 1, 'Each teardown callback should be executed once.')

    def test_unexceptional_code_does_not_trigger_teardown_callbacks(self):
        callbacks = [MagicMock(), MagicMock(), MagicMock()]
        for callback in callbacks:
            self.exception_handler.add_teardown_callback(callback)

        with self.exception_handler:
            pass  # How very unexceptional!

        for callback in callbacks:
            self.assertEqual(callback.call_count, 0, 'No teardown should be executed when code does not raise.')

    def test_system_exit_gets_passed_to_main_thread_from_another_thread(self):

        def call_sys_exit():
            with self.exception_handler:
                sys.exit(123)

        with self.assertRaisesRegex(SystemExit, '123'):
            with self.exception_handler:
                # Note: We use Thread (not SafeThread) here because we're testing UnhandledExceptionHandler directly.
                non_main_thread = Thread(target=call_sys_exit)
                non_main_thread.start()
                non_main_thread.join()

    def test_system_exit_gets_raised_with_code_1_for_any_handled_exception(self):

        def raise_exception():
            with self.exception_handler:
                raise Exception

        expected_exit_code = UnhandledExceptionHandler.HANDLED_EXCEPTION_EXIT_CODE
        with self.assertRaisesRegex(SystemExit, str(expected_exit_code)):
            with self.exception_handler:
                non_main_thread = Thread(target=raise_exception)
                non_main_thread.start()
                non_main_thread.join()

    def test_teardown_callbacks_are_executed_in_reverse_order_of_being_added(self):
        callback = MagicMock()
        self.exception_handler.add_teardown_callback(callback, 'first')
        self.exception_handler.add_teardown_callback(callback, 'second')
        self.exception_handler.add_teardown_callback(callback, 'third')

        with suppress(SystemExit):
            with self.exception_handler:
                raise Exception

        expected_calls_in_reverse_order = [
            call('third'),
            call('second'),
            call('first')]
        self.assertListEqual(callback.call_args_list, expected_calls_in_reverse_order,
                             'Teardown callbacks should be executed in reverse order of being added.')

    def test_initializing_singleton_on_non_main_thread_raises_exception(self):
        exception_raised = False

        def initialize_unhandled_exception_handler():
            # Note: Unfortunately we can't use `self.assertRaises` here since this executes on a different thread.
            # todo: After exceptions in test threads are being caught, simplify this test to use self.assertRaises.
            UnhandledExceptionHandler.reset_singleton()
            try:
                UnhandledExceptionHandler.singleton()
            except Exception:
                nonlocal exception_raised
                exception_raised = True

        # Note: We use Thread (not SafeThread) here because SafeThread uses UnhandledExceptionHandler, which would make
        # the test more complex and fragile.
        non_main_thread = Thread(target=initialize_unhandled_exception_handler)
        non_main_thread.start()
        non_main_thread.join()

        self.assertTrue(exception_raised, 'Exception should be raised when UnhandledExceptionHandler is initialized on '
                                          'a non-main thread.')

    def test_application_info_dump_signal_handler_writes_to_file(self):
        open_mock = mock_open()
        self.patch('app.util.unhandled_exception_handler.open', new=open_mock, create=True)
        self.exception_handler._application_info_dump_signal_handler(process_utils.SIGINFO, MagicMock())

        handle = open_mock()
        assert handle.write.called
