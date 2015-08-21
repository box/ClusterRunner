from unittest.mock import Mock

from app.master.atomizer import Atomizer, AtomizerError
from app.project_type.project_type import ProjectType
from app.util.process_utils import get_environment_variable_setter_command
from test.framework.base_unit_test_case import BaseUnitTestCase


_FAKE_ATOMIZER_COMMAND = 'find . -name test_*.py'
_FAKE_ATOMIZER_COMMAND_OUTPUT = '/tmp/test/directory/test_a.py\n/tmp/test/directory/test_b.py\n/tmp/test/directory/test_c.py\n'
_SUCCESSFUL_EXIT_CODE = 0
_FAILING_EXIT_CODE = 1


class TestAtomizer(BaseUnitTestCase):
    def test_atomizer_returns_expected_atom_list(self):
        mock_project = Mock(spec=ProjectType)
        mock_project.execute_command_in_project.return_value = (_FAKE_ATOMIZER_COMMAND_OUTPUT, _SUCCESSFUL_EXIT_CODE)
        mock_project.project_directory = '/tmp/test/directory'

        atomizer = Atomizer([{'TEST_FILE': _FAKE_ATOMIZER_COMMAND}])
        actual_atoms = atomizer.atomize_in_project(mock_project)
        actual_atom_commands = [atom.command_string for atom in actual_atoms]

        expected_atom_commands = [
            get_environment_variable_setter_command('TEST_FILE', '$PROJECT_DIR/test_a.py'),
            get_environment_variable_setter_command('TEST_FILE', '$PROJECT_DIR/test_b.py'),
            get_environment_variable_setter_command('TEST_FILE', '$PROJECT_DIR/test_c.py'),
        ]
        self.assertListEqual(expected_atom_commands, actual_atom_commands,
                             'List of actual atoms should match list of expected atoms.')
        mock_project.execute_command_in_project.assert_called_once_with(_FAKE_ATOMIZER_COMMAND)

    def test_atomizer_raises_exception_when_atomize_command_fails(self):
        mock_project = Mock(spec=ProjectType)
        mock_project.execute_command_in_project.return_value = ('ERROR ERROR ERROR', _FAILING_EXIT_CODE)

        atomizer = Atomizer([{'TEST_FILE': _FAKE_ATOMIZER_COMMAND}])
        with self.assertRaises(AtomizerError):
            atomizer.atomize_in_project(mock_project)

        mock_project.execute_command_in_project.assert_called_once_with(_FAKE_ATOMIZER_COMMAND)
