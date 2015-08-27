from genty import genty, genty_dataset
from os.path import expanduser, join

from app.master.build_artifact import BuildArtifact
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase

@genty
class TestBuildArtifact(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        Configuration['artifact_directory'] = expanduser('~')

    @genty_dataset(
        happy_path_all_args=(join(expanduser('~'), '1', 'artifact_2_3'), 1, 2, 3),
        override_result_root=(join('override', '1', 'artifact_2_3'), 1, 2, 3, join('override')),
        just_build_directory=(join(expanduser('~'), '1'), 1, None, None),
        build_directory_with_override=(join('override', '1'), 1, None, None, join('override')),
    )
    def test_artifact_directory_returns_proper_artifact_path(self, expected_path, build_id, subjob_id=None,
                                                             atom_id=None, result_root=None):
        self.assertEquals(
            expected_path,
            BuildArtifact._artifact_directory(build_id, subjob_id, atom_id, result_root=result_root),
            'The generated artifact directory is incorrect.'
        )

    @genty_dataset(
        subjob_no_atom=(1, None),
        atom_no_subjob=(None, 1),
    )
    def test_artifact_directory_raises_value_error_if_subjob_id_or_atom_id_specified(self, subjob_id, atom_id):
        with self.assertRaises(ValueError):
            BuildArtifact._artifact_directory(1, subjob_id, atom_id)

    @genty_dataset(
        relative_path=('artifact_0_1', 0, 1),
        absolute_path=('/path/to/build/1/artifact_0_1', 0, 1),
    )
    def test_subjob_and_atom_ids_parses_for_properly_formatted_directory(self, artifact_directory, expected_subjob_id,
                                                                         expected_atom_id):
        subjob_id, atom_id = BuildArtifact._subjob_and_atom_ids(artifact_directory)
        self.assertEquals(subjob_id, expected_subjob_id)
        self.assertEquals(atom_id, expected_atom_id)

    @genty_dataset(
        'artifact_0',
        '/full/path/artifact_0',
        'wrong_0_1',
        'artifact_0_',
    )
    def test_subjob_and_atom_ids_raises_value_error_with_incorrect_format(self, incorrect_artifact_directory):
        with self.assertRaises(ValueError):
            BuildArtifact._subjob_and_atom_ids(incorrect_artifact_directory)

