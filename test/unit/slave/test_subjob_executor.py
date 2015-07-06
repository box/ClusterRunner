from unittest.mock import Mock, mock_open
from os.path import expanduser, join

from app.slave.subjob_executor import SubjobExecutor
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSubjobExecutor(BaseUnitTestCase):

    def test_configure_project_type_passes_project_type_params_and_calls_setup_executor(self):
        project_type_params = {'test': 'value'}
        util = self.patch('app.slave.subjob_executor.util')
        util.create_project_type = Mock(return_value=Mock())
        executor = SubjobExecutor(1)

        executor.configure_project_type(project_type_params)

        util.create_project_type.assert_called_with(project_type_params)
        executor._project_type.setup_executor.assert_called_with()

    def test_configure_project_type_with_existing_project_type_calls_teardown(self):
        executor = SubjobExecutor(1)
        executor._project_type = Mock()
        self.patch('app.slave.subjob_executor.util')

        executor.configure_project_type({})

        executor._project_type.teardown_executor.assert_called_once()

    def test_run_job_config_setup_calls_project_types_run_job_config_setup(self):
        executor = SubjobExecutor(1)
        executor._project_type = Mock()

        executor.run_job_config_setup()

        executor._project_type.run_job_config_setup.assert_called_with()

    def test_execute_subjob_passes_correct_build_executor_index_to_execute_command_in_project(self):
        Configuration['artifact_directory'] = expanduser('~')
        executor = SubjobExecutor(1)
        executor._project_type = Mock()
        executor._project_type.execute_command_in_project = Mock(return_value=(1, 2))
        self.patch('app.slave.subjob_executor.fs_util')
        self.patch('app.slave.subjob_executor.shutil')
        output_file_mock = self.patch('app.slave.subjob_executor.open', new=mock_open(read_data=''), create=True).return_value
        os = self.patch('app.slave.subjob_executor.os')
        os.path = Mock()
        os.path.join = Mock(return_value='path')
        atomic_commands = ['command']
        executor.id = 2
        expected_env_vars = {
            'ARTIFACT_DIR': join(expanduser('~'), '1', 'artifact_2_0'),
            'ATOM_ID': 0,
            'EXECUTOR_INDEX': 2,
            'MACHINE_EXECUTOR_INDEX': 2,
            'BUILD_EXECUTOR_INDEX': 8
        }

        executor.execute_subjob(build_id=1, subjob_id=2, atomic_commands=atomic_commands,
                                base_executor_index=6)

        executor._project_type.execute_command_in_project.assert_called_with('command', expected_env_vars,
                                                                             output_file=output_file_mock)
