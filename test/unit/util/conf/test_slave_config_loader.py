from app.util.conf.slave_config_loader import SlaveConfigLoader
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSlaveConfigLoader(BaseUnitTestCase):

    def test_configure_default_sets_protocol_scheme_to_http(self):
        mock_config_file = self.patch('app.util.conf.base_config_loader.ConfigFile').return_value

        config = Configuration.singleton()
        config_loader = SlaveConfigLoader()
        config_loader.configure_defaults(config)

        key = 'protocol_scheme'
        expected_stored_protocol_scheme_value = 'http'
        actual_stored_protocol_scheme_value = Configuration[key]

        self.assertEqual(expected_stored_protocol_scheme_value, actual_stored_protocol_scheme_value,
                         'The configuration value for the key "{}" was expected to be {}:{}, but was {}:{}.'.format(
                             key, type(expected_stored_protocol_scheme_value), expected_stored_protocol_scheme_value,
                             type(actual_stored_protocol_scheme_value), actual_stored_protocol_scheme_value))

    def test_configure_postload_sets_protocol_scheme_to_https(self):
        mock_config_file = self.patch('app.util.conf.base_config_loader.ConfigFile').return_value
        mock_config_file.read_config_from_disk.return_value = {'general': {'https_cert_file': '/path/to/cert',
                                                                           'https_key_file': '/path/to/key'},
                                                               'slave': {}
                                                              }

        config = Configuration.singleton()
        config_loader = SlaveConfigLoader()
        config_loader.configure_defaults(config)
        config_loader.load_from_config_file(config, config_filename='fake_filename')
        config_loader.configure_postload(config)

        key = 'protocol_scheme'
        expected_stored_protocol_scheme_value = 'https'
        actual_stored_protocol_scheme_value = Configuration[key]

        self.assertEqual(expected_stored_protocol_scheme_value, actual_stored_protocol_scheme_value,
                         'The configuration value for the key "{}" was expected to be {}:{}, but was {}:{}.'.format(
                             key, type(expected_stored_protocol_scheme_value), expected_stored_protocol_scheme_value,
                             type(actual_stored_protocol_scheme_value), actual_stored_protocol_scheme_value))
