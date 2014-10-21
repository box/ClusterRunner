from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.single_use_coin import SingleUseCoin


class TestSingleUseCoin(BaseUnitTestCase):

    def test_coin_spend_returns_true_only_once(self):
        coin = SingleUseCoin()

        self.assertTrue(coin.spend(), 'First call to spend() should return True.')
        self.assertFalse(coin.spend(), 'Subsequent calls to spend() should return False.')
        self.assertFalse(coin.spend(), 'Subsequent calls to spend() should return False.')
