from unittest.mock import MagicMock
from app.master.atomizer import Atomizer, AtomizerError

from app.project_type.project_type import ProjectType
from test.framework.base_unit_test_case import BaseUnitTestCase


_FAKE_ATOMIZER_COMMAND = 'find . -name test_*.py'
_FAKE_ATOMIZER_COMMAND_OUTPUT = './test_a.py\n./test_b.py\n./test_c.py\n'
_SUCCESSFUL_EXIT_CODE = 0
_FAILING_EXIT_CODE = 1


class TestAtomizer(BaseUnitTestCase):
    def test_atomizer_returns_expected_atom_list(self):
        mock_project = MagicMock(spec_set=ProjectType)
        mock_project.execute_command_in_project.return_value = (_FAKE_ATOMIZER_COMMAND_OUTPUT, _SUCCESSFUL_EXIT_CODE)

        atomizer = Atomizer([{'TEST_FILE': _FAKE_ATOMIZER_COMMAND}])
        actual_atoms = atomizer.atomize_in_project(mock_project)

        expected_atoms = ['export TEST_FILE="./test_a.py";',
                          'export TEST_FILE="./test_b.py";',
                          'export TEST_FILE="./test_c.py";']
        self.assertListEqual(expected_atoms, actual_atoms, 'List of actual atoms should match list of expected atoms.')
        mock_project.execute_command_in_project.assert_called_once_with(_FAKE_ATOMIZER_COMMAND)

    def test_atomizer_raises_exception_when_atomize_command_fails(self):
        mock_project = MagicMock(spec_set=ProjectType)
        mock_project.execute_command_in_project.return_value = ('ERROR ERROR ERROR', _FAILING_EXIT_CODE)

        atomizer = Atomizer([{'TEST_FILE': _FAKE_ATOMIZER_COMMAND}])
        with self.assertRaises(AtomizerError):
            atomizer.atomize_in_project(mock_project)

        mock_project.execute_command_in_project.assert_called_once_with(_FAKE_ATOMIZER_COMMAND)
