from genty import genty, genty_dataset

from app.master.build_request_handler import BuildRequestHandler
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestBuildRequestHandler(BaseUnitTestCase):
    @genty_dataset(
        no_subjobs=([], True),
        one_subjob=(['some subjob'], False),
    )
    def test_prepare_build_async_calls_finish_only_if_no_subjobs(self, subjobs, build_finish_called):
        mock_project_lock = self.patch('threading.Lock').return_value
        build_scheduler_mock = self.patch('app.master.build_scheduler.BuildScheduler').return_value
        build_request_handler = BuildRequestHandler(build_scheduler_mock)
        build_mock = self.patch('app.master.build.Build').return_value
        build_mock.has_error = False
        build_mock.all_subjobs.return_value = subjobs

        build_request_handler._prepare_build_async(build_mock, mock_project_lock)

        if build_finish_called:
            build_mock.finish.assert_called_once_with()
        else:
            self.assertFalse(build_mock.finish.called)