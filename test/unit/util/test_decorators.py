from unittest.mock import call

from app.util.decorators import retry_on_exception_exponential_backoff
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestDecorators(BaseUnitTestCase):

    def test_retry_on_exception_exponential_backoff_doesnt_sleep_if_no_exception(self):
        sleep_patch = self.patch('app.util.decorators.time.sleep')

        self.dummy_method_noop()

        self.assertFalse(sleep_patch.called)

    def test_retry_on_exception_exponential_backoff_doesnt_retry_if_incorrect_exception_type(self):
        sleep_patch = self.patch('app.util.decorators.time.sleep')

        with self.assertRaises(RuntimeError):
            self.dummy_method_raises_exception()

        self.assertFalse(sleep_patch.called)

    def test_retry_on_exception_exponential_backoff_retries_with_correct_sleep_durations(self):
        sleep_patch = self.patch('app.util.decorators.time.sleep')

        with self.assertRaises(Exception):
            self.dummy_method_always_raises_exception()

        self.assertEquals(sleep_patch.call_count, 4)
        sleep_patch.assert_has_calls([call(1), call(3), call(9), call(27)], any_order=False)

    def test_retry_on_exception_exponential_backoff_raise_error_if_initial_delay_is_not_positive(self):
        with self.assertRaises(RuntimeError):
            self.dummy_method_noop_with_initial_delay_zero()

    def test_retry_on_exception_exponential_backoff_raise_error_if_exponential_factor_is_less_than_one(self):
        with self.assertRaises(RuntimeError):
            self.dummy_method_noop_with_fraction_exponential_factor()

    @retry_on_exception_exponential_backoff(exceptions=(Exception,))
    def dummy_method_noop(self):
        pass

    @retry_on_exception_exponential_backoff(exceptions=(NameError,))
    def dummy_method_raises_exception(self):
        raise RuntimeError('Runtime error!')

    @retry_on_exception_exponential_backoff(exceptions=(Exception,), initial_delay=1, total_delay=30,
                                            exponential_factor=3)
    def dummy_method_always_raises_exception(self):
        # Retry times should be: 1, 3, 9, 27
        raise Exception('Exception!')

    @retry_on_exception_exponential_backoff(exceptions=(Exception,), initial_delay=0)
    def dummy_method_noop_with_initial_delay_zero(self):
        pass

    @retry_on_exception_exponential_backoff(exceptions=(Exception,), initial_delay=1, total_delay=14,
                                            exponential_factor=0.8)
    def dummy_method_noop_with_fraction_exponential_factor(self):
        pass
