from genty import genty, genty_dataset
import json
import os
from tempfile import mkstemp

import app.util.fs
from app.master.build_artifact import BuildArtifact
from test.framework.base_integration_test_case import BaseIntegrationTestCase


@genty
class TestBuildArtifact(BaseIntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        cls._timing_file_fd, cls._timing_file_path = mkstemp()

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
        app.util.fs.write_file(json.dumps(existing_timing_data), self._timing_file_path)
        build_artifact = BuildArtifact('/some/dir/doesnt/matter')
        build_artifact._update_timing_file(self._timing_file_path, new_timing_data)

        with open(self._timing_file_path, 'r') as timing_file:
            updated_timing_data = json.load(timing_file)

        self.assertDictEqual(updated_timing_data, expected_final_timing_data)
