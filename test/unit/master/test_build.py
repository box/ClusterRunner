from queue import Queue
from unittest.mock import MagicMock

from app.project_type.project_type import ProjectType
from app.master.build import Build, BuildStatus
from app.master.build_request import BuildRequest
from app.master.job_config import JobConfig
from app.master.slave import Slave
from app.master.subjob import Subjob
from app.util import poll
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestBuild(BaseUnitTestCase):

    _FAKE_SLAVE_URL = 'my.favorite.slave.com:40001'
    _FAKE_MAX_EXECUTORS = float('inf')

    def setUp(self):
        super().setUp()
        self.patch('app.master.build.app.util')  # stub out util functions since these often interact with the fs

    def test_allocate_slave_calls_slave_setup(self):
        # arrange
        subjobs = self._create_subjobs()

        mock_project_type = self._create_mock_project_type()
        fake_setup_command = 'docker pull my:leg'
        mock_slave = self._create_mock_slave()

        # act
        build = Build(BuildRequest({'setup': fake_setup_command}))
        build.prepare(subjobs, mock_project_type, self._create_job_config(self._FAKE_MAX_EXECUTORS))
        build.allocate_slave(mock_slave)

        # assert
        mock_slave.setup.assert_called_once_with(build.build_id(), project_type_params={'setup': fake_setup_command})

    def test_allocate_slave_doesnt_use_more_than_max_executors(self):
        subjobs = self._create_subjobs()

        mock_project_type = self._create_mock_project_type()
        fake_setup_command = 'mock command'
        mock_slave = self._create_mock_slave()

        build = Build(BuildRequest({'setup': fake_setup_command}))
        build.prepare(subjobs, mock_project_type, self._create_job_config(1))
        build.allocate_slave(mock_slave)

        self.assertEqual(build._num_allocated_executors, build._max_executors)

    def test_build_status_returns_requested_after_build_creation(self):
        build = Build(BuildRequest({}))
        status = build._status()

        self.assertEqual(status, BuildStatus.QUEUED)

    def test_build_status_returns_queued_after_build_preparation(self):
        subjobs = self._create_subjobs()
        mock_project_type = self._create_mock_project_type()
        build = Build(BuildRequest({}))

        build.prepare(subjobs, mock_project_type, self._create_job_config(self._FAKE_MAX_EXECUTORS))
        status = build._status()

        self.assertEqual(status, BuildStatus.QUEUED)

    def test_build_status_returns_building_after_some_subjobs_are_executing(self):
        subjobs = self._create_subjobs(count=3)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=2)
        build = Build(BuildRequest({}))

        build.prepare(subjobs, mock_project_type, self._create_job_config(self._FAKE_MAX_EXECUTORS))
        build.allocate_slave(mock_slave)  # two out of three subjobs are now "in progress"
        status = build._status()

        self.assertEqual(status, BuildStatus.BUILDING)

    def test_build_status_returns_finished_after_all_subjobs_complete_and_slaves_finished(self):
        subjobs = self._create_subjobs(count=3)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=3)
        build = Build(BuildRequest({}))

        build.prepare(subjobs, mock_project_type, self._create_job_config(self._FAKE_MAX_EXECUTORS))
        build.allocate_slave(mock_slave)  # all three subjobs are now "in progress"

        # Mock out call to create build artifacts after subjobs complete
        build._create_build_artifact = MagicMock()

        for subjob in subjobs:
            build.mark_subjob_complete(subjob.subjob_id())

        # Note: this was never a unit test! We have to wait for a thread to complete post build
        # actions here. TODO: Fix this
        poll.wait_for(lambda: build._postbuild_tasks_are_finished, 5)

        # Verify build artifacts was called after subjobs completed
        build._create_build_artifact.assert_called_once_with()

        build.finish()
        status = build._status()

        self.assertTrue(build._subjobs_are_finished)
        self.assertTrue(build._postbuild_tasks_are_finished)
        self.assertTrue(build._teardowns_finished)

        self.assertEqual(status, BuildStatus.FINISHED)

    def test_need_more_slaves_returns_false_if_max_processes_is_reached(self):
        subjobs = self._create_subjobs(count=5)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=1)
        build = Build(BuildRequest({}))

        build.prepare(subjobs, mock_project_type, self._create_job_config(max_executors=1))
        build.allocate_slave(mock_slave)
        self.assertFalse(build.needs_more_slaves(), "if max processes is reached, we shouldn't need more slaves")

    def test_need_more_slaves_returns_true_if_max_processes_is_not_reached(self):
        subjobs = self._create_subjobs(count=8)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=5)
        build = Build(BuildRequest({}))

        build.prepare(subjobs, mock_project_type, self._create_job_config(max_executors=8))
        build.allocate_slave(mock_slave)
        self.assertTrue(build.needs_more_slaves(), "if max_processes is not reached, we should need more slaves")

    def test_build_cannot_be_prepared_more_than_once(self):
        build = Build(BuildRequest({}))
        subjobs = self._create_subjobs(count=3)
        mock_project_type = self._create_mock_project_type()

        build.prepare(subjobs, mock_project_type, self._create_job_config(max_executors=self._FAKE_MAX_EXECUTORS))

        with self.assertRaises(Exception):
            build.prepare(subjobs, mock_project_type, self._create_job_config(max_executors=self._FAKE_MAX_EXECUTORS))

    def test_runtime_error_when_finishing_unfinished_build(self):
        build = Build(BuildRequest({}))
        build.is_prepared = False
        self.assertRaises(RuntimeError, build.finish)

    def test_teardown_called_on_slave_when_no_subjobs_remain(self):
        build = Build(BuildRequest({}))
        slave = Slave('', 1)
        slave.teardown = MagicMock()
        slave.free_executor = MagicMock(return_value=0)
        build._unstarted_subjobs = Queue()
        build.execute_next_subjob_on_slave(slave)
        slave.teardown.assert_called_with()

    def _create_subjobs(self, count=3):
        return [Subjob(build_id=0, subjob_id=i, project_type=None, job_config=None, atoms=[]) for i in range(count)]

    def _create_job_config(self, max_executors):
        return JobConfig('', '', '', '', '', max_executors)

    def _create_mock_project_type(self):
        return MagicMock(spec_set=ProjectType())

    def _create_mock_slave(self, num_executors=5):
        mock = MagicMock(spec_set=Slave(slave_url=self._FAKE_SLAVE_URL, num_executors=num_executors))
        mock.url = self._FAKE_SLAVE_URL
        mock.num_executors = num_executors
        return mock
