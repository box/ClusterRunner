from unittest.mock import MagicMock

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.unhandled_exception_handler import UnhandledExceptionHandler
from app.util.safe_thread import SafeThread


class TestSafeThread(BaseUnitTestCase):

    def test_exception_on_safe_thread_calls_teardown_callbacks(self):
        my_awesome_teardown_callback = MagicMock()
        unhandled_exception_handler = UnhandledExceptionHandler.singleton()
        unhandled_exception_handler.add_teardown_callback(my_awesome_teardown_callback, 'fake arg', fake_kwarg='boop')

        def my_terrible_method():
            raise Exception('Sic semper tyrannis!')

        thread = SafeThread(target=my_terrible_method)
        thread.start()
        thread.join()

        my_awesome_teardown_callback.assert_called_once_with('fake arg', fake_kwarg='boop')

    def test_normal_execution_on_safe_thread_does_not_call_teardown_callbacks(self):
        my_lonely_teardown_callback = MagicMock()
        unhandled_exception_handler = UnhandledExceptionHandler.singleton()
        unhandled_exception_handler.add_teardown_callback(my_lonely_teardown_callback)

        def my_fantastic_method():
            print('Veritas vos liberabit!')

        thread = SafeThread(target=my_fantastic_method)
        thread.start()
        thread.join()

        self.assertFalse(my_lonely_teardown_callback.called,
                         'The teardown callback should not be called unless an exception is raised.')
