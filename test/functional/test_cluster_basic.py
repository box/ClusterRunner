from box.test.genty import genty, genty_dataset

from test.framework.base_functional_test_case import BaseFunctionalTestCase
from test.framework.functional_test_job_configs import BASIC_FAILING_JOB, BASIC_JOB


@genty
class TestClusterBasic(BaseFunctionalTestCase):

    @genty_dataset(
        basic_job=(BASIC_JOB,),
        basic_failing_job=(BASIC_FAILING_JOB,),
    )
    def test_basic_directory_configs_end_to_end(self, test_job_config):
        master = self.cluster.start_master()
        self.cluster.start_slave()

        build_resp = master.post_new_build({
            'type': 'directory',
            'config': test_job_config.config,
            'project_directory': '/tmp',
        })
        build_id = build_resp['build_id']
        master.block_until_build_finished(build_id)

        if test_job_config.expected_to_fail:
            self.assert_build_has_failure_status(build_id=build_id)
        else:
            self.assert_build_has_successful_status(build_id=build_id)

        self.assert_build_status_contains_expected_data(
            build_id=build_id,
            expected_data={
                'num_atoms': test_job_config.expected_num_atoms,
                'num_subjobs': test_job_config.expected_num_atoms})
        self.assert_build_artifact_contents_match_expected(
            build_id=build_id, expected_build_artifact_contents=test_job_config.expected_artifact_contents)
