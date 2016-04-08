import os
import tempfile
from unittest import skip
import yaml

from genty import genty, genty_dataset

from app.master.build_artifact import BuildArtifact
from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.framework.functional.fs_item import Directory, File
from test.functional.job_configs import BASIC_FAILING_JOB, BASIC_JOB, JOB_WITH_SETUP_AND_TEARDOWN


@genty
class TestClusterBasic(BaseFunctionalTestCase):

    @genty_dataset(
        basic_job=(BASIC_JOB, 'BasicJob'),
        basic_failing_job=(BASIC_FAILING_JOB, 'BasicFailingJob'),
        job_with_setup_and_teardown=(JOB_WITH_SETUP_AND_TEARDOWN, 'JobWithSetupAndTeardown'),
    )
    def test_basic_directory_configs_end_to_end(self, test_job_config, job_name):
        master = self.cluster.start_master()
        slave = self.cluster.start_slave()

        project_dir = tempfile.TemporaryDirectory()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(test_job_config.config[os.name])[job_name],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']
        master.block_until_build_finished(build_id, timeout=30)
        slave.block_until_idle(timeout=20)  # ensure slave teardown has finished before making assertions

        self._assert_build_completed_as_expected(build_id, test_job_config, project_dir)

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
        expected_artifact_contents.append(File(BuildArtifact.ARTIFACT_FILE_NAME))

        self.assert_build_has_successful_status(build_id=build_id)
        self.assert_build_status_contains_expected_data(
            build_id=build_id, expected_data={'num_atoms': 10, 'num_subjobs': 10})
        self.assert_build_artifact_contents_match_expected(
            build_id=build_id, expected_build_artifact_contents=expected_artifact_contents)

    def test_slave_reconnection_does_not_take_down_master(self):
        test_config = JOB_WITH_SETUP_AND_TEARDOWN
        job_config = yaml.safe_load(test_config.config[os.name])['JobWithSetupAndTeardown']
        master = self.cluster.start_master()

        # Start a slave, hard kill it, then reconnect it.
        self.cluster.start_slave(num_executors_per_slave=5, start_port=43001)
        self.cluster.kill_slaves(kill_gracefully=False)

        # Make sure the slave restarts with the same port.
        slave = self.cluster.start_slave(num_executors_per_slave=5, start_port=43001)

        # Start two builds.
        project_dir = tempfile.TemporaryDirectory()
        build_1 = master.post_new_build({
            'type': 'directory',
            'config': job_config,
            'project_directory': project_dir.name,
        })
        build_2 = master.post_new_build({
            'type': 'directory',
            'config': job_config,
            'project_directory': project_dir.name,
        })

        master.block_until_build_finished(build_1['build_id'], timeout=30)
        master.block_until_build_finished(build_2['build_id'], timeout=30)
        slave.block_until_idle(timeout=20)  # ensure slave teardown has finished before making assertions

        self._assert_build_completed_as_expected(build_1['build_id'], test_config, project_dir)
        self._assert_build_completed_as_expected(build_2['build_id'], test_config, project_dir)

    def _assert_build_completed_as_expected(self, build_id, test_job_config, project_dir):
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
            master_api=self.cluster.master_api_client._api,  # todo: Don't use private _api. Add functionality to api_client instead.
            build_id=build_id,
            expected_build_artifact_contents=test_job_config.expected_artifact_contents
        )
        self.assert_directory_contents_match_expected(
            dir_path=project_dir.name, expected_dir_contents=test_job_config.expected_project_dir_contents)
