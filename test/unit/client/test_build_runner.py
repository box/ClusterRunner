from requests.models import Response
from unittest.mock import MagicMock, Mock

from app.client.build_runner import BuildRunner
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestBuildRunner(BaseUnitTestCase):

    def mock_runner_with_status_response(self, response):
        runner = BuildRunner('url', {}, 'mellon')
        start_response = Response()
        start_response.json = MagicMock(return_value={"build_id": "1"})
        runner._network.post = MagicMock(return_value=start_response)
        status_response = Response()
        status_response.json = MagicMock(return_value=response)
        runner._network.get = MagicMock(return_value=status_response)
        runner._download_and_extract_results = MagicMock()
        return runner

    def test_runner_should_request_results_after_build_finishes(self):
        runner = self.mock_runner_with_status_response({"build": {"status": "FINISHED", "result": "NO_FAILURES"}})
        runner.run()
        self.assertTrue(runner._download_and_extract_results.called, 'Client should have tried to download results')

    def test_runner_should_abort_when_status_is_error(self):
        runner = self.mock_runner_with_status_response({"build": {"status": "ERROR"}})
        runner._cancel_build = Mock()

        runner.run()

        self.assertFalse(runner._download_and_extract_results.called,
                         'Client should not have tried to download results')

    def test_runner_should_abort_when_status_is_invalid(self):
        runner = self.mock_runner_with_status_response({"build": "x"})
        runner._cluster_master_api_client.cancel_build = Mock()

        runner.run()

        self.assertFalse(runner._download_and_extract_results.called,
                         'Client should not have tried to download results')
