from unittest.mock import Mock

from genty import genty, genty_dataset

from app.master.atom import Atom
from app.master.atomizer import Atomizer
from app.master.job_config import JobConfig
from app.master.subjob_calculator import SubjobCalculator
from app.project_type.project_type import ProjectType
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestSubjobCalculator(BaseUnitTestCase):
    @genty_dataset(
        atoms_override_specified=(['override1', 'override2'], None, False),
        atoms_override_not_specified=(None, [Atom('atom_value_1'), Atom('atom_value_2')], True),
    )
    def test_compute_subjobs_for_build_only_atomizes_if_override_not_specified(self, atoms_override, atomizer_output,
                                                                               atomizer_called):
        """
        :type atoms_override: list[str] | None
        :type atomizer_output: list[Atom] | None
        :type atomizer_called: bool
        """
        self.patch('os.path.isfile').return_value = False
        mock_project = Mock(spec_set=ProjectType())
        mock_project.atoms_override = atoms_override
        mock_project.timing_file_path.return_value = '/some/path/doesnt/matter'
        mock_project.project_directory = '/some/project/directory'
        mock_atomizer = Mock(spec_set=Atomizer)
        mock_atomizer.atomize_in_project.return_value = atomizer_output
        mock_job_config = Mock(spec=JobConfig)
        mock_job_config.name = 'some_config'
        mock_job_config.max_executors = 1
        mock_job_config.atomizer = mock_atomizer

        subjob_calculator = SubjobCalculator()
        subjob_calculator.compute_subjobs_for_build(build_id=1, job_config=mock_job_config,
                                                    project_type=mock_project)

        self.assertEquals(mock_atomizer.atomize_in_project.called, atomizer_called)
