import os
import tempfile
from unittest import skip

from genty import genty, genty_dataset

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.framework.functional.fs_item import Directory, File
from test.functional.job_configs import BASIC_FAILING_JOB, BASIC_JOB, JOB_WITH_SETUP_AND_TEARDOWN


@genty
class TestClusterBasic(BaseFunctionalTestCase):

    @genty_dataset(
        basic_job=(BASIC_JOB,),
        basic_failing_job=(BASIC_FAILING_JOB,),
        job_with_setup_and_teardown=(JOB_WITH_SETUP_AND_TEARDOWN,),
    )
    def test_basic_directory_configs_end_to_end(self, test_job_config):
        master = self.cluster.start_master()
        slave = self.cluster.start_slave()

        project_dir = tempfile.TemporaryDirectory()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': test_job_config.config[os.name],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']
        master.block_until_build_finished(build_id, timeout=10)
        slave.block_until_idle(timeout=5)  # ensure slave teardown has finished before making assertions

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
        self.assert_directory_contents_match_expected(
            dir_path=project_dir.name, expected_dir_contents=test_job_config.expected_project_dir_contents)

    # TODO: unskip the test when we've changed the default value of `get_project_from_master` to False
    @skip('Skipping for now since this fails on Travis due to the slave being unable to ssh into the master.')
    def test_git_type_demo_project_config(self):
        master = self.cluster.start_master()
        self.cluster.start_slave(num_executors_per_slave=10)

        build_resp = master.post_new_build({
            'type': 'git',
            'url': 'https://github.com/boxengservices/ClusterRunnerDemo.git',
            'job_name': 'Simple',
        })
        build_id = build_resp['build_id']
        master.block_until_build_finished(build_id, timeout=20)  # extra time here to allow for cloning the repo

        # Each atom of the demo project just echoes one of the numbers 1 through 10.
        expected_artifact_contents = [
            Directory('artifact_{}_0'.format(i), [
                File('clusterrunner_command'),
                File('clusterrunner_console_output', contents='{}\n\n'.format(i + 1)),
                File('clusterrunner_exit_code', contents='0\n'),
                File('clusterrunner_time'),
            ])
            for i in range(10)
        ]
        expected_artifact_contents.append(File('results.tar.gz'))

        self.assert_build_has_successful_status(build_id=build_id)
        self.assert_build_status_contains_expected_data(
            build_id=build_id, expected_data={'num_atoms': 10, 'num_subjobs': 10})
        self.assert_build_artifact_contents_match_expected(
            build_id=build_id, expected_build_artifact_contents=expected_artifact_contents)
