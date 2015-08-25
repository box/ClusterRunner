from genty import genty, genty_dataset
import json
import os
import shutil
from tempfile import mkstemp, TemporaryDirectory

from app.util import fs
from app.master.build_artifact import BuildArtifact
from test.framework.base_integration_test_case import BaseIntegrationTestCase


@genty
class TestBuildArtifact(BaseIntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        # For timing file test
        cls._timing_file_fd, cls._timing_file_path = mkstemp()

        # For parsing subjob/atom ids from build artifact test.
        cls._artifact_directory_path = TemporaryDirectory().name
        fs.write_file('0', os.path.join(cls._artifact_directory_path, 'artifact_1_0', 'clusterrunner_exit_code'))
        fs.write_file('1', os.path.join(cls._artifact_directory_path, 'artifact_1_1', 'clusterrunner_exit_code'))
        fs.write_file('0', os.path.join(cls._artifact_directory_path, 'artifact_2_0', 'clusterrunner_exit_code'))
        fs.write_file('1', os.path.join(cls._artifact_directory_path, 'artifact_2_1', 'clusterrunner_exit_code'))

    @classmethod
    def tearDownClass(cls):
        os.close(cls._timing_file_fd)
        os.remove(cls._timing_file_path)

    @genty_dataset(
        mutually_exclusive=({'1': 1, '2': 2}, {'3': 3}, {'1': 1, '2': 2, '3': 3}),
        entire_overlap=({'1': 1, '2': 2}, {'1': 3, '2': 4}, {'1': 3, '2': 4}),
        some_overlap=({'1': 1, '2': 2}, {'2': 4, '3': 5}, {'1': 1, '2': 4, '3': 5}),
    )
    def test_update_timing_file(self, existing_timing_data, new_timing_data, expected_final_timing_data):
        fs.write_file(json.dumps(existing_timing_data), self._timing_file_path)
        build_artifact = BuildArtifact('/some/dir/doesnt/matter')
        build_artifact._update_timing_file(self._timing_file_path, new_timing_data)

        with open(self._timing_file_path, 'r') as timing_file:
            updated_timing_data = json.load(timing_file)

        self.assertDictEqual(updated_timing_data, expected_final_timing_data)

    def test_get_failed_subjob_and_atom_ids_returns_correct_ids(self):
        # Build artifact directory:
        #    artifact_1_0/clusterrunner_exit_code -> 0
        #    artifact_1_1/clusterrunner_exit_code -> 1
        #    artifact_2_0/clusterrunner_exit_code -> 0
        #    artifact_2_1/clusterrunner_exit_code -> 1
        # Expected to return: [(1,1), (2,1)]
        build_artifact = BuildArtifact(self._artifact_directory_path)
        failed_subjob_and_atoms = build_artifact.get_failed_subjob_and_atom_ids()
        self.assertCountEqual(failed_subjob_and_atoms, [(1, 1), (2, 1)])
