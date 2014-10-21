import os
import unittest

from test.framework.base_functional_test_case import BaseFunctionalTestCase


class TestDirectoryBuild(BaseFunctionalTestCase):

    def _paths_for_all_subjobs(self, path, build_id, num_subjobs):
        return [os.path.join(str(build_id), 'artifact_{}_0'.format(str(subjob_id)), path)
                for subjob_id in range(num_subjobs)]

    @unittest.skip
    def test_basic_directory_build(self):
        console_out_path = os.path.join('clusterrunner_console_output')
        num_subjobs = 10

        response_json = self.post_new_build_request({
            'num_subjobs': num_subjobs
        })

        self.assertIn('build_id', response_json, 'API request for new build should return build_id in response.')
        expected_paths = self._paths_for_all_subjobs(console_out_path, response_json['build_id'], num_subjobs)
        self.assert_result_paths_exist(expected_paths)
