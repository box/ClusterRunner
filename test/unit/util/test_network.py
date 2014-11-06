from unittest.mock import Mock

from app.util.network import Network
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestNetwork(BaseUnitTestCase):
    def test_rsa_key_returns_none_if_ssh_keyscan_error(self):
        self._patch_popen_call_to_ssh_keyscan(1, 'some_output', 'some_error"')
        rsa_key = Network._rsa_key('some_host_that_causes_it_to_fail')
        self.assertIsNone(rsa_key)

    def test_rsa_key_returns_output_without_ssh_rsa_str(self):
        self._patch_popen_call_to_ssh_keyscan(0, b"a_host ssh-rsa thebytearray", None)
        rsa_key = Network._rsa_key('a_host')
        self.assertEquals(rsa_key, 'thebytearray')

    def test_is_localhost_returns_false_if_rsa_key_is_none(self):
        self._patch_popen_call_to_ssh_keyscan(1, 'some_output', 'some_error"')
        self.assertFalse(Network.is_localhost('fail'))

    def test_is_localhost_returns_true_if_rsa_keys_match(self):
        self._patch_popen_call_to_ssh_keyscan(0, b"a_host ssh-rsa the_same_byte_array", None)
        self.assertTrue(Network.is_localhost('alias_localhost'))

    def test_is_localhost_returns_false_if_rsa_keys_dont_match(self):
        def popen_side_effect(*args, **kwargs):
            if args[0] == 'ssh-keyscan -t rsa not_localhost':
                mock_popen = Mock()
                mock_popen.communicate.return_value = [b"a_host ssh-rsa the_value_a", None]
                mock_popen.returncode = 0
                return mock_popen
            elif args[0] == 'ssh-keyscan -t rsa localhost':
                mock_popen = Mock()
                mock_popen.communicate.return_value = [b"a_host ssh-rsa the_other_value_b", None]
                mock_popen.returncode = 0
                return mock_popen
            else:
                return None

        popen_patch = self.patch('subprocess.Popen')
        popen_patch.side_effect = popen_side_effect
        self.assertFalse(Network.is_localhost('not_localhost'))

    def _patch_popen_call_to_ssh_keyscan(self, return_code, output, error):
        popen_patch = self.patch('subprocess.Popen')
        popen_patch.return_value.communicate.return_value = [output, error]
        popen_patch.return_value.returncode = return_code
