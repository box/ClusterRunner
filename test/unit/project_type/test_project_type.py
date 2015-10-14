from genty import genty, genty_dataset
from subprocess import TimeoutExpired
from unittest.mock import ANY, MagicMock

from app.master.job_config import JobConfig
from app.project_type.project_type import ProjectType
from app.util.safe_thread import SafeThread
from app.util.unhandled_exception_handler import UnhandledExceptionHandler
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestProjectType(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.mock_popen = self.patch('app.project_type.project_type.Popen_with_delayed_expansion').return_value
        try:
            self.mock_kill = self.patch('os.killpg')
        except AttributeError:
            self.mock_kill = self.patch('os.kill')
        self.mock_temporary_files = []
        self.mock_TemporaryFile = self.patch('app.project_type.project_type.TemporaryFile',
                                             side_effect=self.mock_temporary_files)

    def _mock_next_tempfile(self, contents):
        next_tempfile_mock = MagicMock()
        next_tempfile_mock.read.return_value = contents
        self.mock_temporary_files.append(next_tempfile_mock)

    def _mock_console_output(self, console_output):
        self._mock_next_tempfile(contents=console_output)

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
        job_config = JobConfig('name', 'setup', 'teardown', 'command', 'atomizer', 10, 10)
        project_type = ProjectType()
        project_type.job_config = MagicMock(return_value=job_config)
        project_type.execute_command_in_project = MagicMock(return_value=('', 0))

        project_type.teardown_build()

        project_type.execute_command_in_project.assert_called_with('teardown', timeout=None)

    def test_execute_command_in_project_does_not_choke_on_weird_command_output(self):
        some_weird_output = b'\xbf\xe2\x98\x82'  # the byte \xbf is invalid unicode
        self._mock_console_output(some_weird_output)
        self.mock_popen.returncode = 0

        project_type = ProjectType()
        actual_output, _ = project_type.execute_command_in_project('fake command')

        # Part of this test is just proving that no exception is raised on invalid output.
        self.assertIsInstance(actual_output, str, 'Invalid output from a process should still be converted to string.')

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
        self._mock_console_output(b'fake_output')
        self.mock_popen.pid = 55555
        self._simulate_hanging_popen_process()

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
                self.mock_kill()  # Calling killpg() causes the command thread to end.
                self.fail('project_type.kill_subprocesses should cause the command execution wait loop to exit.')

        self.mock_kill.assert_called_once_with(55555, ANY)  # Note: os.killpg does not accept keyword args.

    def test_command_exiting_normally_will_break_out_of_command_execution_wait_loop(self):
        timeout_exc = TimeoutExpired(cmd=None, timeout=1)
        expected_return_code = 0
        # Simulate Popen.wait() timing out twice before command completes and returns output.
        self.mock_popen.wait.side_effect = [timeout_exc, timeout_exc, expected_return_code]
        self.mock_popen.returncode = expected_return_code
        self._mock_console_output(b'fake_output')

        project_type = ProjectType()
        actual_output, actual_return_code = project_type.execute_command_in_project('echo The power is yours!')

        self.assertEqual(self.mock_kill.call_count, 0, 'os.killpg should not be called when command exits normally.')
        self.assertEqual(actual_output, 'fake_output', 'Output did not contain expected contents.')
        self.assertEqual(actual_return_code, expected_return_code, 'Actual return code should match expected.')
        self.assertTrue(all([file.close.called for file in self.mock_temporary_files]),
                        'All created TemporaryFiles should be closed so that they are removed from the filesystem.')

    def test_timing_out_will_break_out_of_command_execution_wait_loop_and_kill_subprocesses(self):
        mock_time = self.patch('time.time')
        mock_time.side_effect = [0.0, 100.0, 200.0, 300.0]  # time increases by 100 seconds with each loop
        expected_return_code = 1
        self._simulate_hanging_popen_process(fake_returncode=expected_return_code)
        self.mock_popen.pid = 55555
        self._mock_console_output(b'fake output')

        project_type = ProjectType()
        actual_output, actual_return_code = project_type.execute_command_in_project(
            command='sleep 99', timeout=250)

        self.assertEqual(self.mock_kill.call_count, 1, 'os.killpg should be called when execution times out.')
        self.assertEqual(actual_output, 'fake output', 'Output did not contain expected contents.')
        self.assertEqual(actual_return_code, expected_return_code, 'Actual return code should match expected.')
        self.assertTrue(all([file.close.called for file in self.mock_temporary_files]),
                        'All created TemporaryFiles should be closed so that they are removed from the filesystem.')

    def test_exception_raised_while_waiting_causes_termination_and_adds_error_message_to_output(self):
        exception_message = 'Something terribly horrible just happened!'
        value_err_exc = ValueError(exception_message)
        timeout_exc = TimeoutExpired(cmd=None, timeout=1)
        fake_failing_return_code = -15
        # Simulate Popen.wait() timing out twice before raising a ValueError exception.
        self.mock_popen.wait.side_effect = [timeout_exc, timeout_exc, value_err_exc, fake_failing_return_code]
        self.mock_popen.returncode = fake_failing_return_code
        self.mock_popen.pid = 55555
        self._mock_console_output(b'')

        project_type = ProjectType()
        actual_output, actual_return_code = project_type.execute_command_in_project('echo The power is yours!')

        self.assertEqual(self.mock_kill.call_count, 1, 'os.killpg should be called when wait() raises exception.')
        self.assertIn(exception_message, actual_output, 'ClusterRunner exception message should be included in output.')
        self.assertEqual(actual_return_code, fake_failing_return_code, 'Actual return code should match expected.')

    def test_exception_raised_while_waiting_for_termination_adds_error_message_to_output(self):
        mock_time = self.patch('time.time')
        mock_time.side_effect = [0.0, 100.0, 200.0, 300.0]  # time increases by 100 seconds with each loop
        fake_failing_return_code = -15
        self.mock_popen.pid = 55555
        self._mock_console_output(b'')
        exception_message = 'Something terribly horrible just happened!'
        self._simulate_hanging_popen_process(
            fake_returncode=fake_failing_return_code, wait_exception=ValueError(exception_message))

        project_type = ProjectType()
        actual_output, actual_return_code = project_type.execute_command_in_project(
            'echo The power is yours!', timeout=250)

        self.assertIn(exception_message, actual_output, 'ClusterRunner exception message should be included in output.')
        self.assertEqual(actual_return_code, fake_failing_return_code, 'Actual return code should match expected.')

    def test_failing_exit_code_is_injected_when_no_return_code_available(self):
        self.mock_popen.returncode = None  # This will happen if we were not able to terminate the process.
        self._mock_console_output(b'')

        project_type = ProjectType()
        actual_output, actual_return_code = project_type.execute_command_in_project('echo The power is yours!')

        self.assertIsInstance(actual_return_code, int, 'Returned exit code should always be an int.')
        self.assertNotEqual(actual_return_code, 0, 'Returned exit code should be failing (non-zero) when subprocess '
                                                   'returncode is not available.')

    @genty_dataset(
        with_specified_timeout=(30,),
        with_no_timeout=(None,),
    )
    def test_teardown_build_executes_teardown_command(self, expected_timeout):
        project_type = ProjectType()
        mock_execute = MagicMock(return_value=('fake output', 0))
        project_type.execute_command_in_project = mock_execute
        project_type.job_config = MagicMock()

        if expected_timeout:
            project_type.teardown_build(timeout=expected_timeout)
        else:
            project_type.teardown_build()

        mock_execute.assert_called_once_with(ANY, timeout=expected_timeout)

    def _simulate_hanging_popen_process(self, fake_returncode=0, wait_exception=None):
        """
        Replace the Popen.wait() call with a fake implementation that imitates a process that never finishes until it
        is terminated.
        """
        def fake_wait(timeout=None):
            # The fake implementation is that wait() times out forever until os.killpg is called.
            if self.mock_kill.call_count == 0 and timeout is not None:
                raise TimeoutExpired(None, timeout)
            elif self.mock_kill.call_count > 0:
                if wait_exception:
                    raise wait_exception
                return fake_returncode
            self.fail('Popen.wait() should not be called without a timeout before os.killpg has been called.')

        self.mock_popen.wait.side_effect = fake_wait
        self.mock_popen.returncode = fake_returncode

    def test_job_config_uses_passed_in_config_instead_of_clusterrunner_yaml(self):
        config_dict = {
            'commands': ['shell command 1', 'shell command 2;'],
            'atomizers': [{'TESTPATH': 'atomizer command'}],
            'max_executors': 100,
            'max_executors_per_slave': 2,
        }
        project_type = ProjectType(config=config_dict, job_name='some_job_name')

        job_config = project_type.job_config()

        self.assertEquals(job_config.name, 'some_job_name')
        self.assertEquals(job_config.command, 'shell command 1 && shell command 2')
        self.assertEquals(job_config.max_executors, 100)
        self.assertEquals(job_config.max_executors_per_slave, 2)


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
