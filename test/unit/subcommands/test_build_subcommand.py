from app.subcommands.build_subcommand import BuildSubcommand
from app.util.conf.configuration import Configuration
from app.util.secret import Secret
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestBuildSubcommand(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.mock_BuildRunner = self.patch('app.subcommands.build_subcommand.BuildRunner')
        mock_BuildRunner_instance = self.mock_BuildRunner.return_value
        mock_BuildRunner_instance.run.return_value = True
        mock_ServiceRunner = self.patch('app.subcommands.build_subcommand.ServiceRunner')
        self.mock_ServiceRunner_instance = mock_ServiceRunner.return_value
        self.mock_ServiceRunner_instance.run_manager.return_value = None
        self.mock_ServiceRunner_instance.run_worker.return_value = None
        self.mock_ServiceRunner_instance.is_manager_up.return_value = False

    def test_run_starts_services_locally_if_conditions_match(self):
        """
        These conditions are:
            - manager_url is not explicitly specified
            - the manager host is localhost
            - there is only one worker, and it is localhost
        """
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None)
        self.mock_ServiceRunner_instance.run_manager.assert_called_with()
        self.mock_ServiceRunner_instance.run_worker.assert_called_with()

    def test_run_doesnt_start_services_locally_if_manager_is_already_up(self):
        self.mock_ServiceRunner_instance.is_manager_up.return_value = True
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None)
        self.assertFalse(self.mock_ServiceRunner_instance.run_manager.called)
        self.assertFalse(self.mock_ServiceRunner_instance.run_worker.called)

    def test_run_doesnt_start_services_locally_if_configured_manager_hostname_isnt_localhost(self):
        Configuration['manager_hostname'] = 'some_automation_host.pod.box.net:430000'
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None)
        self.assertFalse(self.mock_ServiceRunner_instance.run_manager.called)
        self.assertFalse(self.mock_ServiceRunner_instance.run_worker.called)

    def test_run_doesnt_start_services_locally_if_multiple_workers_configured(self):
        Configuration['workers'] = ['host_1.pod.box.net', 'host_2.pod.box.net']
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None)
        self.assertFalse(self.mock_ServiceRunner_instance.run_manager.called)
        self.assertFalse(self.mock_ServiceRunner_instance.run_worker.called)

    def test_run_doesnt_start_services_locally_if_single_worker_configured_that_isnt_localhost(self):
        Configuration['workers'] = ['host_2.pod.box.net']
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None)
        self.assertFalse(self.mock_ServiceRunner_instance.run_manager.called)
        self.assertFalse(self.mock_ServiceRunner_instance.run_worker.called)

    def test_run_instantiates_buildrunner_with_correct_constructor_args_for_git_project_type(self):
        Configuration['hostname'] = 'localhost'
        Configuration['port'] = 43000
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None, type='git')
        # assert on constructor params
        self.mock_BuildRunner.assert_called_once_with(
            'localhost:43000',
            request_params={'type': 'git'},
            secret=Secret.get()
        )

    def test_run_instantiates_buildrunner_with_correct_constructor_args_for_directory_project_type(self):
        Configuration['hostname'] = 'localhost'
        Configuration['port'] = 43000
        os_getcwd_patch = self.patch('os.getcwd')
        os_getcwd_patch.return_value = '/current/directory'
        build_subcommand = BuildSubcommand()
        build_subcommand.run(None, None)
        # assert on constructor params
        self.mock_BuildRunner.assert_called_once_with(
            'localhost:43000',
            request_params={'type':'directory', 'project_directory':'/current/directory'},
            secret=Secret.get()
        )