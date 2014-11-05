from app.util.conf.base_config_loader import BaseConfigLoader
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestBaseConfigLoader(BaseUnitTestCase):

    def test_list_type_conf_file_values_are_correctly_converted_to_lists(self):
        conf = Configuration.singleton()
        conf.set('some_list', ['localhost'])  # The previous conf value determines the expected type: a list.
        conf_file_value = 'my-lonely-slave'  # ConfigObj parses value to a string type if only one element is specified.

        config_loader = BaseConfigLoader()
        config_loader._cast_and_set('some_list', conf_file_value, conf)

        expected_conf_setting = [conf_file_value]
        self.assertListEqual(conf.get('some_list'), expected_conf_setting,
                             'The config loader should convert string values into single element lists for conf keys '
                             'that are expected to be of type list.')
