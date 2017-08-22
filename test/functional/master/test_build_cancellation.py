import os
import subprocess
import tempfile
import time
from unittest import skipIf
import yaml

from app.master.build_fsm import BuildState
from app.util import poll
from app.util.process_utils import is_windows
from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import JOB_WITH_SLEEPS_90SEC, JOB_WITH_SLEEPING_ATOMIZER_90SEC


ATOMIZER_PID_FILE='/tmp/atomizer_pid.txt'

@skipIf(is_windows(), 'Fails on AppVeyor; see issue #345')
class TestBuildCancellation(BaseFunctionalTestCase):
    def test_build_cancellation_while_building(self):
        master = self.cluster.start_master()
        # Only one slave, with one executor. This means that the slave should be able to
        # theoretically finish the build in 90 seconds, as this job definition has 90 atoms,
        # with each sleeping for 1 second.
        slaves = self.cluster.start_slaves(1, num_executors_per_slave=1, start_port=43001)
        project_dir = tempfile.TemporaryDirectory()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(JOB_WITH_SLEEPS_90SEC.config[os.name])['SleepingJob90Sec'],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']
        self.assertTrue(master.block_until_build_started(build_id, timeout=30),
                        'The build should start building within the timeout.')
        self.assert_build_status_contains_expected_data(build_id, {'status': BuildState.BUILDING})
        master.cancel_build(build_id)
        self.assertTrue(master.block_until_build_canceled(build_id, timeout=30),
                        'The build should be canceled within the timeout.')
        self.assert_build_status_contains_expected_data(build_id, {'status': BuildState.CANCELED})
        # Make sure that slave becomes idle before the total job execution time (90 sec).
        # Which means the build is canceled and aborted before it can finish.
        # So here total maximum timeout we have is
        #   30 (block_until_build_canceled)
        # + 10 (block_until_idle)
        # = 40 sec; which is less than the build execution time (i.e. 90 sec)
        self.assertTrue(slaves[0].block_until_idle(timeout=10),
                        'The slave should become idle within the timeout.')

    def test_build_cancellation_while_atomizing(self):
        self._remove_file(ATOMIZER_PID_FILE)
        master = self.cluster.start_master()
        # Start a slave even though its not needed as build is canceled during atomization
        slaves = self.cluster.start_slaves(1, num_executors_per_slave=1, start_port=43001)
        project_dir = tempfile.TemporaryDirectory()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(JOB_WITH_SLEEPING_ATOMIZER_90SEC.config[os.name])['SleepingAtomizerJob90Sec'],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']
        self.assertTrue(master.block_until_build_has_status(build_id, [BuildState.QUEUED], timeout=30),
                        'The build should be in queued state within the timeout.')
        self.assert_build_status_contains_expected_data(build_id, {'status': BuildState.QUEUED})
        self.assertTrue(self._block_until_file_present(ATOMIZER_PID_FILE, timeout=30),
                        'The atomizer subprocess should be started withtin the timeout.')
        atomizer_pid = self._get_pid_from_file(ATOMIZER_PID_FILE)
        self.assertTrue(isinstance(atomizer_pid, int),
                        'Invalid atomizer pid retrieved from the file {}.'.format(ATOMIZER_PID_FILE))
        master.cancel_build(build_id)
        self.assertTrue(master.block_until_build_canceled(build_id, timeout=30),
                        'The build should be canceled within the timeout.')
        # Make sure that the atomizer subprocess is killed before its total execution time (90 sec).
        # Here the total maximum timeout we have is
        #   30 (block_until_build_canceled)
        # + 30 (_block_until_process_is_killed)
        # = 60 sec; which is less than the atomizer subprocess execution time (i.e. 90 sec)
        self.assertTrue(self._block_until_process_is_killed(atomizer_pid, timeout=30),
                        'The atomizer subprocess should be killed within the timeout.')
        self.assert_build_status_contains_expected_data(build_id, {'status': BuildState.CANCELED})
        # Make sure that slave is in idle state
        self.assertTrue(slaves[0].is_slave_idle(),
                        'The slave should be idle.')

    def _block_until_file_present(self, file_name: str, timeout: int=None) -> bool:
        """
        Poll until file is created.
        :param file_name: Absolute path of the file to check
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :return: Whether the file is present
        """
        def is_file_present():
            return os.path.isfile(file_name)

        return poll.wait_for(is_file_present, timeout_seconds=timeout)

    def _block_until_process_is_killed(self, pid: int, timeout: int=None) -> bool:
        """
        Poll until process with pid does not exists.
        :param pid: Process id of the process
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :return: Whether the process exists
        """
        def check_pid():
            """
            Check For the existence of a unix pid.
            """
            # Sending signal 0 to a pid will raise an OSError exception if the pid is not running,
            # and do nothing otherwise.
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            return True

        return poll.wait_for(check_pid, timeout_seconds=timeout)

    def _remove_file(self, file_name):
        try:
            os.remove(file_name)
        except FileNotFoundError:
            pass

    def _get_pid_from_file(self, file_name):
        with open(file_name) as f:
            line = f.readline()
            s = line.split()
            return int(s[0])
