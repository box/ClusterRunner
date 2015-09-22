from unittest.mock import Mock
from app.master.atom import Atom, AtomState
from app.master.job_config import JobConfig
from app.master.subjob import Subjob
from app.project_type.project_type import ProjectType
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSubjob(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self._job_config_command = 'fake command'
        self._subjob = Subjob(
            build_id=12,
            subjob_id=34,
            project_type=Mock(spec_set=ProjectType),
            job_config=Mock(spec=JobConfig, command=self._job_config_command),
            atoms=[
                Atom(
                    'export BREAKFAST="pancakes";',
                    expected_time=23.4,
                    actual_time=56.7,
                    exit_code=1,
                    state=AtomState.NOT_STARTED,
                    atom_id=0,
                ),
                Atom(
                    'export BREAKFAST="cereal";',
                    expected_time=89.0,
                    actual_time=24.6,
                    exit_code=0,
                    state=AtomState.NOT_STARTED,
                    atom_id=1,
                ),
            ],
        )

    def test_subjob_constructor_sets_subjob_id_on_atoms(self):
        atoms = [Mock(), Mock()]
        Subjob(build_id=1, subjob_id=4, project_type=Mock(), job_config=Mock(), atoms=atoms)
        for atom in atoms:
            self.assertEqual(atom.subjob_id, 4)

    def test_api_representation_matches_expected(self):
        actual_api_repr = self._subjob.api_representation()

        expected_api_repr = {
            'id': 34,
            'command': self._job_config_command,
            'slave': None,
            'atoms': [
                {
                    'id': 0,
                    'command_string': 'export BREAKFAST="pancakes";',
                    'expected_time': 23.4,
                    'actual_time': 56.7,
                    'exit_code': 1,
                    'state': 'NOT_STARTED',
                    'subjob_id': 34
                },
                {
                    'id': 1,
                    'command_string': 'export BREAKFAST="cereal";',
                    'expected_time': 89.0,
                    'actual_time': 24.6,
                    'exit_code': 0,
                    'state': 'NOT_STARTED',
                    'subjob_id': 34
                },
            ]
        }
        self.assertEqual(actual_api_repr, expected_api_repr, 'Actual api representation should match expected.')

    def _assert_atoms_are_in_state(self, api_repr, state_str):
        for atom_dict in api_repr['atoms']:
            self.assertEqual(atom_dict['state'], state_str)

    def test_mark_in_progress_marks_all_atoms_in_progress(self):
        self._subjob.mark_in_progress(None)
        actual_api_repr = self._subjob.api_representation()
        self._assert_atoms_are_in_state(actual_api_repr, 'IN_PROGRESS')

    def test_mark_completed_marks_all_atoms_completed(self):
        self._subjob.mark_completed()
        actual_api_repr = self._subjob.api_representation()
        self._assert_atoms_are_in_state(actual_api_repr, 'COMPLETED')
