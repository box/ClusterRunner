import os
import tempfile
from unittest import skip
import yaml

from genty import genty, genty_dataset

from app.common.build_artifact import BuildArtifact
from app.manager.build import BuildStatus
from app.manager.worker import WorkerRegistry
from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.framework.functional.fs_item import Directory, File
from test.functional.job_configs import BASIC_FAILING_JOB, BASIC_JOB, FAILING_SETUP_JOB, JOB_WITH_SETUP_AND_TEARDOWN


@genty
class TestClusterBasic(BaseFunctionalTestCase):

    @genty_dataset(
        basic_job=(BASIC_JOB, 'BasicJob'),
        basic_failing_job=(BASIC_FAILING_JOB, 'BasicFailingJob'),
        job_with_setup_and_teardown=(JOB_WITH_SETUP_AND_TEARDOWN, 'JobWithSetupAndTeardown'),
    )
    def test_basic_directory_configs_end_to_end(self, test_job_config, job_name):
        manager = self.cluster.start_manager()
        worker = self.cluster.start_worker()

        project_dir = tempfile.TemporaryDirectory()
        build_resp = manager.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(test_job_config.config[os.name])[job_name],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']
        self.assertTrue(manager.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')
        worker.block_until_idle(timeout=20)  # ensure worker teardown has finished before making assertions

        self._assert_build_completed_as_expected(build_id, test_job_config, project_dir)

    # TODO: unskip the test when we've changed the default value of `get_project_from_manager` to False
    @skip('Skipping for now since this fails on Travis due to the worker being unable to ssh into the manager.')
    def test_git_type_demo_project_config(self):
        manager = self.cluster.start_manager()
        self.cluster.start_worker(num_executors_per_worker=10)

        build_resp = manager.post_new_build({
            'type': 'git',
            'url': 'https://github.com/boxengservices/ClusterRunnerDemo.git',
            'job_name': 'Simple',
        })
        build_id = build_resp['build_id']
        self.assertTrue(manager.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')

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
        expected_artifact_contents.append(File(BuildArtifact.ARTIFACT_TARFILE_NAME))
        expected_artifact_contents.append(File(BuildArtifact.ARTIFACT_ZIPFILE_NAME))

        self.assert_build_has_successful_status(build_id=build_id)
        self.assert_build_status_contains_expected_data(
            build_id=build_id, expected_data={'num_atoms': 10, 'num_subjobs': 10})
        self.assert_build_artifact_contents_match_expected(
            build_id=build_id, expected_build_artifact_contents=expected_artifact_contents)

    def test_worker_reconnection_does_not_take_down_manager(self):
        WorkerRegistry.reset_singleton()
        test_config = JOB_WITH_SETUP_AND_TEARDOWN
        job_config = yaml.safe_load(test_config.config[os.name])['JobWithSetupAndTeardown']
        manager = self.cluster.start_manager()

        # Start a worker, hard kill it, then reconnect it.
        self.cluster.start_worker(num_executors_per_worker=5, start_port=43001)
        self.cluster.kill_workers(kill_gracefully=False)

        # Make sure the worker restarts with the same port.
        worker = self.cluster.start_worker(num_executors_per_worker=5, start_port=43001)

        # Start two builds.
        project_dir_1 = tempfile.TemporaryDirectory()
        build_1 = manager.post_new_build({
            'type': 'directory',
            'config': job_config,
            'project_directory': project_dir_1.name,
        })
        project_dir_2 = tempfile.TemporaryDirectory()
        build_2 = manager.post_new_build({
            'type': 'directory',
            'config': job_config,
            'project_directory': project_dir_2.name,
        })

        self.assertTrue(manager.block_until_build_finished(build_1['build_id'], timeout=45),
                        'Build 1 should finish building within the timeout.')
        self.assertTrue(manager.block_until_build_finished(build_2['build_id'], timeout=45),
                        'Build 2 should finish building within the timeout.')
        worker.block_until_idle(timeout=20)  # ensure worker teardown has finished before making assertions

        self._assert_build_completed_as_expected(build_1['build_id'], test_config, project_dir_1)
        self._assert_build_completed_as_expected(build_2['build_id'], test_config, project_dir_2)

    def test_failed_setup_does_not_kill_worker(self):
        manager = self.cluster.start_manager()
        worker = self.cluster.start_worker()

        project_dir = tempfile.TemporaryDirectory()
        build_resp = manager.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(FAILING_SETUP_JOB.config[os.name])['FailingSetupJob'],
            'project_directory': project_dir.name,
        })

        build_id = build_resp['build_id']
        self.assertTrue(manager.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')

        workers = manager.get_workers()['workers']
        build = manager.get_build_status(build_id)['build']
        self.assertGreater(build['num_subjobs'], 0)
        self.assertTrue(all(worker['is_alive'] for worker in workers),
                        'Worker should not die even though setup failed.')
        self.assertEqual(build['status'], BuildStatus.ERROR)

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
            manager_api=self.cluster.manager_api_client._api,  # todo: Don't use private _api. Add functionality to api_client instead.
            build_id=build_id,
            expected_build_artifact_contents=test_job_config.expected_artifact_contents
        )
        self.assert_directory_contents_match_expected(
            dir_path=project_dir.name, expected_dir_contents=test_job_config.expected_project_dir_contents)
