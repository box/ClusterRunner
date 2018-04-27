import os
import tempfile
import yaml

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import JOB_WITH_SETUP_AND_TEARDOWN


class TestShutdown(BaseFunctionalTestCase):

    def test_shutdown_all_workers_should_kill_and_remove_all_workers(self):
        manager = self.cluster.start_manager()
        self.cluster.start_workers(2)

        manager.graceful_shutdown_all_workers()

        workers_response = manager.get_workers()
        workers = workers_response['workers']

        self.assertEqual(0, len(workers))

        self.cluster.block_until_n_workers_dead(2, 10)

    def test_shutdown_one_worker_should_leave_one_worker_alive_and_remove_shutdowned_worker(self):
        manager = self.cluster.start_manager()
        self.cluster.start_workers(2)

        manager.graceful_shutdown_workers_by_id([1])

        workers_response = manager.get_workers()
        workers = workers_response['workers']
        living_workers = [worker for worker in workers if worker['is_alive']]

        self.assertEqual(1, len(living_workers))
        self.assertEqual(1, len(workers))

        self.cluster.block_until_n_workers_dead(1, 10)

    def test_shutdown_all_workers_while_build_is_running_should_finish_build_then_kill_and_remove_workers(self):
        manager = self.cluster.start_manager()
        self.cluster.start_workers(2)

        project_dir = tempfile.TemporaryDirectory()
        build_resp = manager.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(JOB_WITH_SETUP_AND_TEARDOWN.config[os.name])['JobWithSetupAndTeardown'],
            'project_directory': project_dir.name,
            })
        build_id = build_resp['build_id']
        self.assertTrue(manager.block_until_build_started(build_id, timeout=30),
                        'The build should start building within the timeout.')

        # Shutdown one on the workers and test if the build can still complete
        manager.graceful_shutdown_workers_by_id([1])

        self.assertTrue(manager.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')
        self.assert_build_has_successful_status(build_id=build_id)

        workers_response = manager.get_workers()
        workers = workers_response['workers']
        living_workers = [worker for worker in workers if worker['is_alive']]

        self.assertEqual(1, len(living_workers))
        self.assertEqual(1, len(workers))
