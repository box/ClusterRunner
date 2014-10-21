from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestConfiguration(BaseUnitTestCase):

    _test_conf_values = {
        'Family': 'Stegosauridae',
        'Genus': 'Tuojiangosaurus',
        'Species': 'multispinus',
    }

    def setUp(self):
        super().setUp()
        self.mock_base_config = self.patch('app.util.conf.base_config_loader.BaseConfigLoader')

    def test_conf_values_can_be_set_via_set_method(self):
        conf = Configuration.singleton()
        for conf_key, conf_value in self._test_conf_values.items():
            conf.set(conf_key, conf_value)

        self._assert_conf_values_match_expected(self._test_conf_values)

    def test_conf_values_can_be_set_via_keyed_access(self):
        for conf_key, conf_value in self._test_conf_values.items():
            Configuration[conf_key] = conf_value

        self._assert_conf_values_match_expected(self._test_conf_values)

    def _assert_conf_values_match_expected(self, expected_conf_values):
        conf = Configuration.singleton()
        for conf_key, expected_conf_value in expected_conf_values.items():
            self.assertEqual(expected_conf_value, conf.get(conf_key),
                             'Actual conf value via get() should match expected.')
            self.assertEqual(expected_conf_value, Configuration[conf_key],
                             'Actual conf value via keyed access should match expected.')
