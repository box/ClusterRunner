from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import BASIC_JOB


class TestMasterEndpoints(BaseFunctionalTestCase):

    def test_cancel_build(self):
        master = self.cluster.start_master()

        build_resp = master.post_new_build({
            'type': 'directory',
            'config': BASIC_JOB.config,
            'project_directory': '/tmp',
            })
        build_id = build_resp['build_id']
        master.cancel_build(build_id)
        master.block_until_build_finished(build_id)

        self.assert_build_has_canceled_status(build_id=build_id)

