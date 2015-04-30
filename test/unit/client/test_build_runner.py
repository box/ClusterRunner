from requests.models import Response
from unittest.mock import MagicMock, Mock, call

from app.client.build_runner import BuildRunner
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestBuildRunner(BaseUnitTestCase):

    def _create_build_runner_instance(self, response):
        mock_get_logger = self.patch('app.client.build_runner.get_logger')
        logger = mock_get_logger.return_value

        build_id = '1'

        runner = BuildRunner('url', {}, 'mellon')
        start_response = Response()
        start_response.json = MagicMock(return_value={'build_id': build_id})
        runner._network.post = MagicMock(return_value=start_response)
        status_response = Response()
        status_response.json = MagicMock(return_value=response)
        runner._network.get = MagicMock(return_value=status_response)
        runner._download_and_extract_results = MagicMock()
        return runner, logger, build_id

    def _assert_build_runner_logs_properly(
            self,
            mock_logger,
            expected_log_info_args=None,
            expected_log_warning_args=None,
            expected_log_error_args=None,
    ):
        self.assertEqual(mock_logger.info.call_args_list, expected_log_info_args or [])
        self.assertEqual(mock_logger.warning.call_args_list, expected_log_warning_args or [])
        self.assertEqual(mock_logger.error.call_args_list, expected_log_error_args or [])

    def test_runner_should_request_results_after_build_finishes(self):
        build_result = 'NO_FAILURES'
        runner, logger, build_id = self._create_build_runner_instance({
            'build': {
                'status': 'FINISHED',
                'result': build_result,
            },
        })
        runner.run()

        self._assert_build_runner_logs_properly(
            mock_logger=logger,
            expected_log_info_args=[
                call('Build is running. (Build id: {})', build_id),
                call('Build is finished. (Build id: {})', build_id),
                call('Build {} result was {}'.format(build_id, build_result)),
            ],
        )
        self.assertTrue(runner._download_and_extract_results.called, 'Client should have tried to download results')

    def test_runner_should_abort_when_status_is_error(self):
        runner, logger, build_id = self._create_build_runner_instance({'build': {'status': 'ERROR'}})
        runner._cancel_build = Mock()

        runner.run()

        self._assert_build_runner_logs_properly(
            mock_logger=logger,
            expected_log_info_args=[call('Build is running. (Build id: {})', build_id)],
            expected_log_warning_args=[call('Script aborted due to error!')],
            expected_log_error_args=[call('Build aborted due to error: None')],
        )
        self.assertFalse(runner._download_and_extract_results.called,
                         'Client should not have tried to download results')

    def test_runner_should_abort_when_status_is_invalid(self):
        runner, logger, build_id = self._create_build_runner_instance({'build': 'x'})
        runner._cluster_master_api_client.cancel_build = Mock()

        runner.run()

        self._assert_build_runner_logs_properly(
            mock_logger=logger,
            expected_log_info_args=[call('Build is running. (Build id: {})', build_id)],
            expected_log_warning_args=[
                call('Script aborted due to error!'),
                call('Cancelling build {}'.format(build_id)),
            ],
            expected_log_error_args=[
                call('Status response does not contain a "build" object with a '
                     '"status" value.URL: http://url/v1/build/1, Content:{\'build\': \'x\'}'
                ),
            ],
        )
        self.assertFalse(runner._download_and_extract_results.called,
                         'Client should not have tried to download results')
