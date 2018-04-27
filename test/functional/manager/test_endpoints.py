import os
import tempfile

import yaml

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import BASIC_JOB


class TestManagerEndpoints(BaseFunctionalTestCase):

    def setUp(self):
        super().setUp()
        self._project_dir = tempfile.TemporaryDirectory()

    def _start_manager_only_and_post_a_new_job(self):
        manager = self.cluster.start_manager()
        build_resp = manager.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(BASIC_JOB.config[os.name])['BasicJob'],
            'project_directory': self._project_dir.name,
            })
        build_id = build_resp['build_id']
        return manager, build_id

    def test_cancel_build(self):
        manager, build_id = self._start_manager_only_and_post_a_new_job()

        manager.cancel_build(build_id)
        self.assertTrue(manager.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')

        self.assert_build_has_canceled_status(build_id=build_id)

    def test_get_artifact_before_it_is_ready(self):
        manager, build_id = self._start_manager_only_and_post_a_new_job()

        # Since we didn't start any workers so the artifacts is actually not ready.
        _, status_code = manager.get_build_artifacts(build_id)
        self.assertEqual(status_code, 202)

        # Cancel the started build just to speed up teardown (avoid teardown timeout waiting for empty queue)
        manager.cancel_build(build_id)
