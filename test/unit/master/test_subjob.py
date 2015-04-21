from unittest.mock import Mock
from app.master.atom import Atom
from app.master.job_config import JobConfig

from app.master.subjob import Subjob
from app.project_type.project_type import ProjectType
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSubjob(BaseUnitTestCase):

    def test_api_representation_matches_expected(self):
        job_config_command = 'fake command'
        subjob = Subjob(
            build_id=12,
            subjob_id=34,
            project_type=Mock(spec_set=ProjectType),
            job_config=Mock(spec=JobConfig, command=job_config_command),
            atoms=[
                Atom('BREAKFAST', 'pancakes', expected_time=23.4, actual_time=56.7),
                Atom('BREAKFAST', 'cereal', expected_time=89.0, actual_time=24.6),
            ],
        )

        actual_api_repr = subjob.api_representation()

        expected_api_repr = {
            'id': 34,
            'command': job_config_command,
            'atoms': [
                {'id': 0, 'atom': 'export BREAKFAST="pancakes";', 'expected_time': 23.4, 'actual_time': 56.7},
                {'id': 1, 'atom': 'export BREAKFAST="cereal";', 'expected_time': 89.0, 'actual_time': 24.6},
            ]
        }
        self.assertEqual(actual_api_repr, expected_api_repr, 'Actual api representation should match expected.')
