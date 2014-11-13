from box.test.genty import genty, genty_dataset
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, ANY

from app.master.job_config import JobConfig
from app.project_type.project_type import ProjectType
from app.util.safe_thread import SafeThread
from app.util.unhandled_exception_handler import UnhandledExceptionHandler
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestProjectType(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.mock_popen = self.patch('app.project_type.project_type.Popen').return_value

    def test_required_constructor_args_are_correctly_detected_without_defaults(self):
        actual_required_args = _FakeEnvWithoutDefaultArgs.required_constructor_argument_names()
        expected_required_args = ['earth', 'wind', 'water', 'fire', 'heart']
        self.assertListEqual(actual_required_args, expected_required_args)

    def test_required_constructor_args_are_correctly_detected_with_defaults(self):
        actual_required_args = _FakeEnvWithDefaultArgsAndDocs.required_constructor_argument_names()
        expected_required_args = ['earth', 'wind', 'water']
        self.assertListEqual(actual_required_args, expected_required_args)

    @genty_dataset(
        arg_with_standard_doc=('earth', 'doc for earth param', True, None),
        arg_with_multiline_param_doc=('wind', 'doc for wind param...', True, None),
        arg_with_no_type_doc=('water', 'doc for water param', True, None),
        optional_arg_with_no_param_doc=('fire', None, False, 'flaming'),
        optional_arg_with_no_docs=('heart', None, False, 'bleeding'),
    )
    def test_constructor_args_info_returns_expected_data(
            self,
            arg_name,
            expected_help_string,
            expected_required_flag,
            expected_default_value,
    ):
        arguments_info = _FakeEnvWithDefaultArgsAndDocs.constructor_arguments_info()
        argument_info = arguments_info[arg_name]

        self.assertEqual(argument_info.help, expected_help_string,
                         'Actual help string should match expected.')
        self.assertEqual(argument_info.required, expected_required_flag,
                         'Actual required flag should match expected.')
        self.assertEqual(argument_info.default, expected_default_value,
                         'Actual default value for argument should match expected.')

    def test_teardown_build_runs_teardown(self):
        job_config = JobConfig('name', 'setup', 'teardown', 'command', 'atomizer', 10)
        project_type = ProjectType()
        project_type.job_config = MagicMock(return_value=job_config)
        project_type.execute_command_in_project = MagicMock(return_value=('', 0))

        project_type.teardown_build()

        project_type.execute_command_in_project.assert_called_with('teardown')

    def test_execute_command_in_project_does_not_choke_on_weird_command_output(self):
        some_weird_output = b'\xbf\xe2\x98\x82'  # the byte \xbf is invalid unicode
        self.mock_popen.communicate.return_value = (some_weird_output, None)
        self.mock_popen.returncode = (some_weird_output, None)

        project_type = ProjectType()
        project_type.execute_command_in_project('fake command')
        # test is successful if no exception is raised!

    @genty_dataset(
        no_blacklist=(['earth', 'wind', 'water'], None, True),
        with_blacklist=(['earth'], ['earth'], False),
        with_blacklist_others_exist=(['wind', 'water'], ['earth'], True)
    )
    def test_constructor_argument_info_with_blacklist(
            self,
            args_to_check,
            blacklist,
            expected):
        project_type = _FakeEnvWithDefaultArgsAndDocs('dirt', 'breeze', 'drop')
        arg_mapping = project_type.constructor_arguments_info(blacklist)
        for arg_name in args_to_check:
            self.assertEqual(arg_name in arg_mapping, expected)

    def test_calling_kill_subprocesses_will_break_out_of_command_execution_wait_loop(self):

        def fake_communicate(timeout=None):
            # The fake implementation is that communicate() times out forever until os.killpg is called.
            if mock_killpg.call_count == 0 and timeout is not None:
                raise TimeoutExpired(None, timeout)
            elif mock_killpg.call_count > 0:
                return b'fake output', b'fake error'
            self.fail('Popen.communicate() should not be called without a timeout before os.killpg has been called.')

        mock_killpg = self.patch('os.killpg')
        self.mock_popen.communicate.side_effect = fake_communicate
        self.mock_popen.returncode = 1
        self.mock_popen.pid = 55555
        project_type = ProjectType()
        command_thread = SafeThread(target=project_type.execute_command_in_project, args=('echo The power is yours!',))

        # This calls execute_command_in_project() on one thread, and calls kill_subprocesses() on another. The
        # kill_subprocesses() call should cause the first thread to exit.
        command_thread.start()
        project_type.kill_subprocesses()

        # This *should* join immediately, but we specify a timeout just in case something goes wrong so that the test
        # doesn't hang. A successful join implies success. We also use the UnhandledExceptionHandler so that exceptions
        # propagate from the child thread to the test thread and fail the test.
        with UnhandledExceptionHandler.singleton():
            command_thread.join(timeout=10)
            if command_thread.is_alive():
                mock_killpg()  # Calling killpg() causes the command thread to end.
                self.fail('project_type.kill_subprocesses should cause the command execution wait loop to exit.')

        mock_killpg.assert_called_once_with(55555, ANY)  # Note: os.killpg does not accept keyword args.

    def test_command_exiting_normally_will_break_out_of_command_execution_wait_loop(self):
        mock_killpg = self.patch('os.killpg')
        timeout_exc = TimeoutExpired(None, 1)

        # Simulate Popen.communicate() timing out twice before command completes and returns output.
        self.mock_popen.communicate.side_effect = [timeout_exc, timeout_exc, (b'fake_output', b'fake_error')]
        self.mock_popen.returncode = 0
        self.mock_popen.pid = 55555

        project_type = ProjectType()
        actual_return_output, actual_return_code = project_type.execute_command_in_project('echo The power is yours!')

        self.assertEqual(mock_killpg.call_count, 0, 'os.killpg should not be called when command exits normally.')
        self.assertEqual(actual_return_output, 'fake_output\nfake_error', 'Output should contain stdout and stderr.')


class _FakeEnvWithoutDefaultArgs(ProjectType):
    def __init__(self, earth, wind, water, fire, heart):
        super().__init__()


class _FakeEnvWithDefaultArgsAndDocs(ProjectType):
    def __init__(self, earth, wind, water, fire='flaming', heart='bleeding'):
        """
        When your powers combine, I am... excited?
        (Note: The below parameter docs are intentionally inconsistent.)

        :param earth: doc for earth param
        :type earth: EarthObject
        :param wind: doc for wind param...
            and some other documentation we'd expect not to be exposed.
        :type wind: WindObject
        :param water: doc for water param
        :type fire: Fire Object
        :return: the captain of the planet
        :rtype: Captain
        """
        super().__init__()
