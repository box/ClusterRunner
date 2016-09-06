import os
import tempfile

import yaml

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import BASIC_JOB


class TestMasterEndpoints(BaseFunctionalTestCase):

    def setUp(self):
        super().setUp()
        self._project_dir = tempfile.TemporaryDirectory()

    def _start_master_only_and_post_a_new_job(self):
        master = self.cluster.start_master()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(BASIC_JOB.config[os.name])['BasicJob'],
            'project_directory': self._project_dir.name,
            })
        build_id = build_resp['build_id']
        return master, build_id

    def test_cancel_build(self):
        master, build_id = self._start_master_only_and_post_a_new_job()

        master.cancel_build(build_id)
        master.block_until_build_finished(build_id)

        self.assert_build_has_canceled_status(build_id=build_id)

    def test_get_artifact_before_it_is_ready(self):
        master, build_id = self._start_master_only_and_post_a_new_job()

        # Since we didn't start any slaves so the artifacts is actually not ready.
        _, status_code = master.get_build_artifacts(build_id)
        self.assertEqual(status_code, 202)

        # Cancel the started build just to speed up teardown (avoid teardown timeout waiting for empty queue)
        master.cancel_build(build_id)
