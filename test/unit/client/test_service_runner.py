from unittest.mock import Mock

from app.client.service_runner import ServiceRunner, ServiceRunError
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestServiceRunner(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.mock_Popen = self.patch('app.client.service_runner.Popen')
        self.mock_Network = self.patch('app.client.service_runner.Network')
        self.mock_time = self.patch('app.client.service_runner.time')

    def test_run_master_invokes_popen(self):
        self.mock_time.time.side_effect = range(1000)
        mock_network = self.mock_Network.return_value
        mock_network.get.return_value = Mock(ok=False)
        try:
            service_runner = ServiceRunner('frodo:1')
            service_runner.run_master()
        except ServiceRunError:
            pass

        assert self.mock_Popen.called

    def test_run_master_does_not_invoke_popen_if_resp_is_ok(self):
        mock_network = self.mock_Network.return_value
        mock_network.get.return_value = Mock(ok=True)
        try:
            service_runner = ServiceRunner('frodo:1')
            service_runner.run_master()
        except ServiceRunError:
            pass

        assert  not self.mock_Popen.called
