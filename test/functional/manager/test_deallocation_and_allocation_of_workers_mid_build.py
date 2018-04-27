import os
import tempfile
from unittest import skipIf
import yaml

from app.util.process_utils import is_windows
from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import JOB_WITH_SLEEPS


@skipIf(is_windows(), 'Fails on AppVeyor; see issue #345')
class TestDeallocationAndAllocationOfWorkersMidBuild(BaseFunctionalTestCase):
    def test_build_completes_after_allocating_deallocating_and_reallocating_workers_to_build(self):
        manager = self.cluster.start_manager()
        # Only one worker, with one executor. This means that the worker should be able to
        # theoretically finish the build in 5 seconds, as this job definition has 5 atoms,
        # with each sleeping for 1 second.
        self.cluster.start_workers(1, num_executors_per_worker=1, start_port=43001)
        project_dir = tempfile.TemporaryDirectory()
        build_resp = manager.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(JOB_WITH_SLEEPS.config[os.name])['BasicSleepingJob'],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']
        self.assertTrue(manager.block_until_build_started(build_id, timeout=30),
                        'The build should start building within the timeout.')
        manager.graceful_shutdown_workers_by_id([1])
        self.cluster.block_until_n_workers_dead(num_workers=1, timeout=10)
        self.cluster.kill_workers(kill_gracefully=False)
        self.assert_build_status_contains_expected_data(build_id, {'status': 'BUILDING'})
        self.cluster.start_workers(1, num_executors_per_worker=1, start_port=43001)
        self.assertTrue(manager.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')
        self.assert_build_has_successful_status(build_id)
