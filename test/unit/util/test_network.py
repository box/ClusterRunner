import socket
from unittest.mock import Mock

from genty import genty, genty_dataset

from app.util.network import Network
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestNetwork(BaseUnitTestCase):

    _do_network_mocks = False  # Disable network-related patches (in BaseUnitTestCase) so we can test the patched code.

    def setUp(self):
        super().setUp()
        self._hostname = 'host_name'
        self._ip = '8.8.8.8'

    def _patch_socket_gethostbyname(self, side_effect):
        get_host_by_name = self.patch('socket.gethostbyname')
        get_host_by_name.side_effect = side_effect
        self._mock_get_host_by_name = get_host_by_name

    def test_get_host_id_returns_none_if_gaierror(self):
        self._patch_socket_gethostbyname(side_effect=socket.gaierror)
        self.assertIsNone(Network.get_host_id(self._hostname))
        self._mock_get_host_by_name.assert_called_once_with(self._hostname)

    def test_get_host_id_returns_ip_of_the_host(self):
        self._patch_socket_gethostbyname(side_effect=[self._ip])
        self.assertEqual(Network.get_host_id(self._hostname), self._ip)
        self._mock_get_host_by_name.assert_called_once_with(self._hostname)

    @genty_dataset(
        get_host1_alias_id_failed=(
            {
                'host1': 'host1_id',
                'host1-alias': None,
            },
            False
        ),
        get_host1_id_failed=(
            {
                'host1': None,
                'host1-alias': 'host1_id',
            },
            False,
        ),
        get_host1_and_host1_alias_ids_failed=(
            {
                'host1': None,
                'host1-alias': None,
            },
            False
        ),
        host1_and_host1_alias_having_same_host_id=(
            {
                'host1': 'host1_id',
                'host1-alias': 'host1_id',
            },
            True,
        ),
        host_1_and_not_host1_alias_having_different_host_ids=(
            {
                'host1': 'host1_id',
                'not-host1-alias': 'host2_id',
            },
            False,
        ),
    )
    def test_are_hosts_same(
            self,
            host_to_id,
            expect_hosts_are_same,
    ):
        def side_effect(host):
            host_id = host_to_id[host]
            if host_id is None:
                raise socket.gaierror
            else:
                return host_id

        self._patch_socket_gethostbyname(side_effect=side_effect)
        self.assertEqual(Network.are_hosts_same(*host_to_id), expect_hosts_are_same)

    def test_get_host_id_of_localhost(self):  # todo: this is an integration test -- move it to integration dir
        local_host_name = socket.gethostname()
        self.assertEqual(
            Network.get_host_id('localhost'),
            Network.get_host_id(local_host_name),
            'Host id of "localhost" is not the same as host id of "{}"'.format(local_host_name),
        )

