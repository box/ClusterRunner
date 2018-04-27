from genty import genty, genty_dataset

from app.util.conf.base_config_loader import BaseConfigLoader, InvalidConfigError
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class _FakeConfigLoader(BaseConfigLoader):
    def _get_config_file_whitelisted_keys(self):
        return ['some_bool', 'some_int', 'some_list', 'some_str']

    def configure_defaults(self, conf):
        super().configure_defaults(conf)
        conf.set('some_bool', True)
        conf.set('some_int', 1776)
        conf.set('some_list', ['red', 'white', 'blue'])
        conf.set('some_str', 'America!')
        conf.set('some_nonwhitelisted_key', 1492)


@genty
class TestBaseConfigLoader(BaseUnitTestCase):

    @genty_dataset(
        bool_type=('some_bool', 'False', False),
        int_type=('some_int', '1999', 1999),
        list_type=('some_list', ['a', 'b', 'c'], ['a', 'b', 'c']),
        str_type=('some_str', 'OneTwoThree', 'OneTwoThree'),
    )
    def test_all_datatypes_can_be_overridden_by_value_in_file(self, key, parsed_val, expected_stored_conf_val):
        mock_config_file = self.patch('app.util.conf.base_config_loader.ConfigFile').return_value
        mock_config_file.read_config_from_disk.return_value = {'general': {key: parsed_val}}
        config = Configuration.singleton()

        config_loader = _FakeConfigLoader()
        config_loader.configure_defaults(config)
        config_loader.load_from_config_file(config, config_filename='fake_filename')

        actual_stored_conf_val = Configuration[key]
        self.assertEqual(expected_stored_conf_val, actual_stored_conf_val,
                         'The configuration value for the key "{}" was expected to be {}:{}, but was {}:{}.'.format(
                             key, type(expected_stored_conf_val), expected_stored_conf_val,
                             type(actual_stored_conf_val), actual_stored_conf_val))

    @genty_dataset(
        nonexistent_key=('some_nonexistent_key', '1999'),
        nonwhitelisted_key=('some_nonwhitelisted_key', '2001'),
    )
    def test_error_is_raised_when_conf_file_contains_nonexistent_or_nonwhitelisted_key(self, key, parsed_val):
        mock_config_file = self.patch('app.util.conf.base_config_loader.ConfigFile').return_value
        mock_config_file.read_config_from_disk.return_value = {'general': {key: parsed_val}}
        config = Configuration.singleton()

        config_loader = _FakeConfigLoader()
        config_loader.configure_defaults(config)

        with self.assertRaises(InvalidConfigError):
            config_loader.load_from_config_file(config, config_filename='fake_filename')

    def test_list_type_conf_file_values_are_correctly_converted_to_lists(self):
        conf = Configuration.singleton()
        conf.set('some_list', ['localhost'])  # The previous conf value determines the expected type: a list.
        conf_file_value = 'my-lonely-worker'  # ConfigObj parses value to a string type if only one element is specified.

        config_loader = BaseConfigLoader()
        config_loader._cast_and_set('some_list', conf_file_value, conf)

        expected_conf_setting = [conf_file_value]
        self.assertListEqual(conf.get('some_list'), expected_conf_setting,
                             'The config loader should convert string values into single element lists for conf keys '
                             'that are expected to be of type list.')
