from argparse import ArgumentParser
from genty import genty, genty_dataset
import signal
from threading import Event
from unittest.mock import Mock, MagicMock, patch

from app.project_type.project_type import ProjectType
from app.subcommands.build_subcommand import BuildSubcommand
from app.util.conf.configuration import Configuration
from app.util.secret import Secret
import main
from test.framework.base_unit_test_case import BaseUnitTestCase
from test.framework.comparators import AnythingOfType


@genty
class TestMain(BaseUnitTestCase):

    _HOSTNAME = 'bbaggins.local'

    _FAKE_MASTER = 'localhost:43000'
    _FAKE_SLAVE = 'localhost:43001'
    _PROJECT_DIRECTORY = 'workspace'

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.write_file')
        self.mock_tornado = self.patch('app.subcommands.service_subcommand.tornado')
        self.mock_ClusterMaster = self.patch('app.subcommands.master_subcommand.ClusterMaster')
        self.mock_ClusterSlave = self.patch('app.subcommands.slave_subcommand.ClusterSlave')
        self.mock_ClusterMasterApplication = self.patch('app.subcommands.master_subcommand.ClusterMasterApplication')
        self.mock_ClusterSlaveApplication = self.patch('app.subcommands.slave_subcommand.ClusterSlaveApplication')
        self.mock_BuildRunner = self.patch('app.subcommands.build_subcommand.BuildRunner')
        self.mock_ServiceRunner = self.patch('app.subcommands.build_subcommand.ServiceRunner')
        self.mock_ConfigFile = self.patch('main.ConfigFile')
        self.patch('main.SlaveConfigLoader')
        self.patch('app.util.conf.base_config_loader.platform').node.return_value = self._HOSTNAME
        self.patch('app.subcommands.master_subcommand.analytics.initialize')
        self.patch('argparse._sys.stderr')  # Hack to prevent argparse from printing output during tests.

        # We want the method _start_app_force_kill_countdown mocked out for every test *except* one, so we are patching
        # this method in an uglier way that allows us to unpatch it just for that test.
        self.start_force_kill_countdown_patcher = patch('main._start_app_force_kill_countdown')
        self.start_force_kill_countdown_mock = self.start_force_kill_countdown_patcher.start()

    def test_master_args_correctly_create_cluster_master(self):
        mock_cluster_master = self.mock_ClusterMaster.return_value  # get the mock for the ClusterMaster instance

        main.main(['master'])

        self.mock_ClusterMaster.assert_called_once_with()  # assert on constructor params
        self.mock_ClusterMasterApplication.assert_called_once_with(mock_cluster_master)  # assert on constructor params

    def test_default_slave_args_correctly_create_cluster_slave(self):
        self.mock_configuration_values({'num_executors': 1}, default_value='default_value')
        mock_cluster_slave = self.mock_ClusterSlave.return_value

        main.main(['slave'])

        expected_cluster_slave_constructor_args = {
            'num_executors': 1,
            'port': Configuration['port'],
            'host': Configuration['hostname'],
        }
        self.mock_ClusterSlave.assert_called_once_with(**expected_cluster_slave_constructor_args)
        self.mock_ClusterSlaveApplication.assert_called_once_with(mock_cluster_slave)

    def test_explicit_slave_args_correctly_create_cluster_slave(self):
        mock_cluster_slave = self.mock_ClusterSlave.return_value

        main.main(['slave', '--num-executors', '5', '--port', '98765'])

        expected_cluster_slave_constructor_args = {
            'num_executors': 5,
            'port': 98765,
            'host': Configuration['hostname'],
        }
        self.mock_ClusterSlave.assert_called_once_with(**expected_cluster_slave_constructor_args)
        self.mock_ClusterSlaveApplication.assert_called_once_with(mock_cluster_slave)

    @genty_dataset(
        only_required_args_passed=(
            ['imaginary', '--hero-name', 'bilbo'],
            {'type': 'imaginary', 'hero_name': 'bilbo'}),
        required_and_optional_args_passed=(
            ['imaginary', '--hero-name', 'bilbo', '--party-size', '12'],
            {'type': 'imaginary', 'hero_name': 'bilbo', 'party_size': '12'}),
        one_remote_file=(
            ['--remote-file', 'hello', 'fake_url', 'imaginary', '--hero-name', 'drizzt'],
            {'type': 'imaginary', 'hero_name': 'drizzt', 'remote_files': {'hello': 'fake_url'}}
        ),
        multiple_remote_files=(
            ['--remote-file', 'hello', 'hello_url', '--remote-file', 'goodbye', 'goodbye_url',
             'imaginary', '--hero-name', 'drizzt'],
            {'type': 'imaginary', 'hero_name': 'drizzt',
             'remote_files': {'hello': 'hello_url', 'goodbye': 'goodbye_url'}}
        )
    )
    def test_valid_args_for_build_will_correctly_instantiate_build_runner(self, extra_args, expected_request_params):
        def secret_setter(*args):
            Secret.set('mellon1234')
        main._set_secret = Mock(side_effect=secret_setter)
        build_args = ['build', '--master-url', 'smaug:1'] + extra_args
        expected_request_params['job_name'] = None
        self.patch('main.util.project_type_subclasses_by_name').return_value = {  # mock out project_type subclasses
            'imaginary': _ImaginaryProjectType,
        }

        main.main(build_args)
        self.mock_BuildRunner.assert_called_once_with(master_url='smaug:1',
                                                      request_params=expected_request_params, secret='mellon1234')

    def test_main_exits_with_nonzero_exit_code_if_build_runner_fails(self):
        mock_Secret = self.patch('app.subcommands.build_subcommand.Secret')
        mock_Secret.get.return_value = 'mellon1234'
        mock_build_runner = self.mock_BuildRunner.return_value
        mock_build_runner.run.return_value = False  # run() method returns false when build fails
        build_subcommand = BuildSubcommand()
        with self.assertRaisesRegex(SystemExit, '1'):  # asserts that sys.exit(1) is called
            build_subcommand.run(log_level=None, master_url='smaug:1', build_type='middleearth',
                                 some_other_param='999')

        self.mock_BuildRunner.assert_called_once_with(
            master_url='smaug:1',
            secret='mellon1234',
            request_params={'type': 'middleearth', 'some_other_param': '999'}
        )

    def test_single_machine_case_runs_master_and_slave(self):
        mock_service_runner = self.mock_ServiceRunner.return_value
        mock_service_runner.is_master_up.return_value = False
        build_args = ['build']

        main.main(build_args)

        self.assertTrue(mock_service_runner.run_master.called)
        self.assertTrue(mock_service_runner.run_slave.called)

    def test_build_subcommand_no_args_sets_cwd_in_request_params_to_build_runner(self):
        expected_project_directory = 'mordor'
        self.mock_cwd(expected_project_directory)
        bs = BuildSubcommand()
        bs.run(log_level='whatever', master_url=None)
        # the second member of call args are the keyword arguments
        # so this checks the kw args to the constructor for BuildRunner
        actual = self.mock_build_runner_constructor_kw_args()['request_params']['project_directory']
        self.assertEqual(expected_project_directory, actual)

    def test_all_project_type_command_line_args_should_be_documented_with_help_text(self):
        mock_build_parser = MagicMock(spec_set=ArgumentParser)

        main._add_project_type_subparsers(mock_build_parser)

        mock_project_type_parsers = mock_build_parser.add_subparsers.return_value.add_parser.return_value
        add_argument_calls = mock_project_type_parsers.add_argument.call_args_list
        for add_argument_args, add_argument_kwargs in add_argument_calls:
            argument_name = add_argument_args[0]
            has_argument_help_text = bool(add_argument_kwargs.get('help'))
            self.assertTrue(has_argument_help_text,
                            'All arguments (including "{}") should have help text specified.'.format(argument_name))

    @genty_dataset(
        ['-V'], ['--version'], ['master'], ['slave', '-p', '12345'], ['build', '--master-url', 'shire.middle-earth.org']
    )
    def test_parse_args_accepts_valid_arguments(self, valid_arg_set):
        try:
            main._parse_args(valid_arg_set)  # Test succeeds if no exception is raised.
        except SystemExit as ex:
            if ex.code != 0:  # Test also succeeds if SystemExit is raised with "successful" exit code of 0.
                raise

    @genty_dataset(
        no_args=([],),
        prefix_of_valid_arg=(['slave', '--master', 'shire.middle-earth.org'],),
        nonexistent_arg=(['hobbitses'],),
    )
    def test_parse_args_rejects_invalid_arguments(self, invalid_arg_set):
        rgx_anything_but_zero = r'[^0]'
        with self.assertRaisesRegex(
                SystemExit, rgx_anything_but_zero,
                msg='Executing _parse_args on a set of invalid args should raise SystemExit with a non-zero exit code.'
        ):
            main._parse_args(invalid_arg_set)

    def test_start_app_force_kill_countdown_is_called_when_app_exits_normally(self):
        self.patch('main.MasterSubcommand')  # causes subcommand run() method to return immediately

        main.main(['master'])

        self.start_force_kill_countdown_mock.assert_called_once_with(seconds=AnythingOfType(int))

    def test_start_app_force_kill_countdown_is_called_when_app_exits_via_unhandled_exception(self):
        run_mock = self.patch('main.MasterSubcommand').return_value.run
        run_mock.side_effect = Exception('I am here to trigger teardown handlers!')

        with self.assertRaises(SystemExit, msg='UnhandledExceptionHandler should convert Exception to SystemExit.'):
            main.main(['master'])

        self.start_force_kill_countdown_mock.assert_called_once_with(seconds=AnythingOfType(int))

    def test_start_app_force_kill_countdown_sends_self_sigkill_after_delay(self):
        # Since the countdown logic executes asynchronously on a separate thread, we replace os.kill() with this
        # callback to both capture the os.kill() args and set an event to signal us that async execution finished.
        def fake_os_exit(*args):
            nonlocal os_exit_args, os_exit_called_event
            os_exit_args = args
            os_exit_called_event.set()

        mock_os = self.patch('main.os')
        mock_time = self.patch('main.time')
        self.start_force_kill_countdown_patcher.stop()  # unpatch this method so we can test it
        pid_of_self = 12345
        sleep_duration = 15
        os_exit_args = None
        os_exit_called_event = Event()
        mock_os.getpid.return_value = pid_of_self
        mock_os._exit.side_effect = fake_os_exit

        main._start_app_force_kill_countdown(seconds=sleep_duration)

        # Wait for the async thread to finish executing.
        self.assertTrue(os_exit_called_event.wait(timeout=5), 'os._exit should be called within a few seconds.')
        mock_time.sleep.assert_called_once_with(sleep_duration)
        self.assertEqual(os_exit_args, (1,), 'The force kill countdown should exit the process with exit status 1.')

    def mock_cwd(self, current_dir=None):
        mock_os = self.patch('app.subcommands.build_subcommand.os')
        mock_os.getcwd.return_value = current_dir or self._PROJECT_DIRECTORY

    def mock_build_runner_constructor_kw_args(self):
        return self.mock_BuildRunner.call_args[1]

    def mock_configuration_values(self, custom_dictionary, default_value=None):
        mock_configuration = self.patch('app.util.conf.configuration.Configuration')
        mock_get = lambda key: custom_dictionary.get(key, default_value)
        mock_configuration.singleton.return_value.get.side_effect = mock_get


class _ImaginaryProjectType(ProjectType):
    def __init__(self, hero_name, party_size=13):
        super().__init__()
