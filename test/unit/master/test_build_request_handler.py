from genty import genty, genty_dataset

from app.master.atomizer import AtomizerError
from app.master.build_fsm import BuildState
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
        build_mock.is_stopped = False
        build_mock.get_subjobs.return_value = subjobs

        build_request_handler._prepare_build_async(build_mock, mock_project_lock)

        if build_finish_called:
            build_mock.finish.assert_called_once_with()
        else:
            self.assertFalse(build_mock.finish.called)

    def test_prepare_build_async_does_not_call_finish_for_canceled_or_error_build(self):
        subjobs = []
        mock_project_lock = self.patch('threading.Lock').return_value
        build_scheduler_mock = self.patch('app.master.build_scheduler.BuildScheduler').return_value
        build_request_handler = BuildRequestHandler(build_scheduler_mock)
        build_mock = self.patch('app.master.build.Build').return_value
        build_mock.is_stopped = True # this means the BuildState is CANCELED or ERROR
        build_mock.get_subjobs.return_value = subjobs

        build_request_handler._prepare_build_async(build_mock, mock_project_lock)

        self.assertFalse(build_mock.finish.called, 'Build finish should not be called for CANCELED build')

    @genty_dataset(
        no_subjobs=([],),
        one_subjob=(['some subjob'],),
    )
    def test_prepare_build_async_does_not_call_mark_failed_for_canceled_build(self, subjobs):
        mock_project_lock = self.patch('threading.Lock').return_value
        build_scheduler_mock = self.patch('app.master.build_scheduler.BuildScheduler').return_value
        build_request_handler = BuildRequestHandler(build_scheduler_mock)
        build_mock = self.patch('app.master.build.Build').return_value
        build_mock.get_subjobs.return_value = subjobs
        build_mock.is_canceled = True
        build_mock.prepare.side_effect = AtomizerError

        build_request_handler._prepare_build_async(build_mock, mock_project_lock)

        self.assertFalse(build_mock.mark_failed.called, 'Build mark_failed should not be called for CANCELED build')
