import os
import tempfile

import yaml

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import JOB_WITH_SETUP_AND_TEARDOWN


class TestConsoleOutput(BaseFunctionalTestCase):

    def setUp(self):
        super().setUp()
        self.project_dir = tempfile.TemporaryDirectory()

    def test_logs_are_still_available_after_slave_goes_offline(self):
        master = self.cluster.start_master()
        self.cluster.start_slave()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(JOB_WITH_SETUP_AND_TEARDOWN.config[os.name])['JobWithSetupAndTeardown'],
            'project_directory': self.project_dir.name,
        })
        build_id = build_resp['build_id']
        self.assertTrue(master.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')
        self.assert_build_has_successful_status(build_id)

        # Bring down the single slave and assert that console output for the build is still available.
        self.cluster.kill_slaves()

        console_output_1 = master.get_console_output(build_id=build_id, subjob_id=0, atom_id=0)
        self.assertEqual(
            console_output_1['content'].strip(),
            'Doing subjob 1.'
        )
        console_output_2 = master.get_console_output(build_id=build_id, subjob_id=1, atom_id=0)
        self.assertEqual(
            console_output_2['content'].strip(),
            'Doing subjob 2.'
        )
