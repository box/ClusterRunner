from queue import Queue
from os.path import abspath, join
import sys
from threading import Event
from unittest.mock import MagicMock, Mock, mock_open, call
from genty import genty, genty_dataset

from app.master.atom import Atom, AtomState
from app.master.atomizer import Atomizer
from app.master.build import Build, BuildStatus, BuildProjectError
from app.master.build_artifact import BuildArtifact
from app.master.build_request import BuildRequest
from app.master.job_config import JobConfig
from app.master.slave import Slave
from app.master.subjob import Subjob
from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestBuild(BaseUnitTestCase):

    _FAKE_SLAVE_URL = 'my.favorite.slave.com:40001'
    _FAKE_MAX_EXECUTORS = sys.maxsize
    _FAKE_MAX_EXECUTORS_PER_SLAVE = sys.maxsize
    _FAKE_PAYLOAD = {'filename': 'pizza_order.txt', 'body': 'Four large pepperoni, one small cheese.'}

    def setUp(self):
        super().setUp()
        Configuration['results_directory'] = abspath(join('some', 'temp', 'directory'))

        self.patch('app.master.build.BuildArtifact.__new__')  # patch __new__ to mock instances but keep static methods
        self.mock_util = self.patch('app.master.build.app.util')  # stub out util - it often interacts with the fs
        self.mock_open = self.patch('app.master.build.open', autospec=False, create=True)

    def test_allocate_slave_calls_slave_setup(self):
        mock_slave = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.PREPARED)

        build.allocate_slave(mock_slave)

        mock_slave.setup.assert_called_once_with(build)

    def test_build_doesnt_use_more_than_max_executors(self):
        mock_slaves = [self._create_mock_slave(num_executors=5) for _ in range(3)]  # 15 total available executors
        expected_num_executors_used = 12  # We expect the build to use 12 out of 15 available executors.
        job_config = self._create_job_config(max_executors=expected_num_executors_used)
        build = self._create_test_build(BuildStatus.PREPARED, job_config=job_config)
        build.execute_next_subjob_or_teardown_slave = MagicMock()

        for mock_slave in mock_slaves:
            build.allocate_slave(mock_slave)
            build.begin_subjob_executions_on_slave(mock_slave)

        self.assertEqual(build.execute_next_subjob_or_teardown_slave.call_count, expected_num_executors_used,
                         'Build should start executing as many subjobs as its max_executors setting.')

    def test_build_doesnt_use_more_than_max_executors_per_slave(self):
        mock_slaves = [self._create_mock_slave(num_executors=5) for _ in range(3)]
        max_executors_per_slave = 2
        job_config = self._create_job_config(max_executors_per_slave=max_executors_per_slave)
        build = self._create_test_build(build_status=BuildStatus.PREPARED, job_config=job_config)
        build.execute_next_subjob_or_teardown_slave = Mock()

        for mock_slave in mock_slaves:
            build.allocate_slave(mock_slave)
            build.begin_subjob_executions_on_slave(mock_slave)

        # Even though each slave has 5 executors, we should only start subjobs on 2 of those executors per slave.
        expected_subjob_execution_calls = [
            call(mock_slaves[0]),
            call(mock_slaves[0]),
            call(mock_slaves[1]),
            call(mock_slaves[1]),
            call(mock_slaves[2]),
            call(mock_slaves[2]),
        ]
        self.assertEqual(
            build.execute_next_subjob_or_teardown_slave.mock_calls,
            expected_subjob_execution_calls,
            'Build should start executing as many subjobs per slave as its max_executors_per_slave setting.')

    def test_build_status_returns_queued_after_build_creation(self):
        build = self._create_test_build()

        self.assertEqual(build._status(), BuildStatus.QUEUED,
                         'Build status should be QUEUED immediately after build has been created.')

    def test_build_status_returns_queued_after_build_preparation(self):
        build = self._create_test_build(BuildStatus.PREPARED)

        self.assertEqual(build._status(), BuildStatus.QUEUED,
                         'Build status should be QUEUED after build has been prepared.')

    def test_build_status_returns_building_after_setup_has_started(self):
        mock_slave = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.PREPARED)

        build.allocate_slave(mock_slave)

        self.assertEqual(build._status(), BuildStatus.BUILDING,
                         'Build status should be BUILDING after setup has started on slaves.')

    def test_build_status_returns_building_after_setup_is_complete_and_subjobs_are_executing(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertEqual(build._status(), BuildStatus.BUILDING,
                         'Build status should be BUILDING after subjobs have started executing on slaves.')

    def test_build_status_returns_finished_after_all_subjobs_complete_and_slaves_finished(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        build._create_build_artifact = MagicMock()

        self._finish_test_build(build)

        # Verify build artifacts was called after subjobs completed
        build._create_build_artifact.assert_called_once_with()
        self.assertTrue(build._subjobs_are_finished)
        self.assertEqual(build._status(), BuildStatus.FINISHED)

    def test_complete_subjob_parses_payload_and_stores_value_in_atom_objects(self):
        fake_atom_exit_code = 777
        mock_open(mock=self.mock_open, read_data=str(fake_atom_exit_code))
        build = self._create_test_build(BuildStatus.BUILDING, num_subjobs=1, num_atoms_per_subjob=1)
        subjob = build.all_subjobs()[0]

        build.complete_subjob(subjob.subjob_id(), payload=self._FAKE_PAYLOAD)

        expected_payload_sys_path = join(Configuration['results_directory'], '1', 'artifact_0_0')
        self.mock_open.assert_called_once_with(
            join(expected_payload_sys_path, BuildArtifact.EXIT_CODE_FILE),
            'r',
        )
        self.assertEqual(subjob.atoms[0].exit_code, fake_atom_exit_code)

    def test_complete_subjob_marks_atoms_of_subjob_as_completed(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        subjob = build.all_subjobs()[0]

        build.complete_subjob(subjob.subjob_id(), payload=self._FAKE_PAYLOAD)

        for atom in subjob.atoms:
            self.assertEqual(AtomState.COMPLETED, atom.state)

    def test_complete_subjob_writes_and_extracts_payload_to_correct_directory(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        subjob = build.all_subjobs()[0]

        payload = {'filename': 'turtles.txt', 'body': 'Heroes in a half shell.'}
        build.complete_subjob(subjob.subjob_id(), payload=payload)

        expected_payload_sys_path = join(Configuration['results_directory'], '1', 'turtles.txt')
        self.mock_util.fs.write_file.assert_called_once_with('Heroes in a half shell.', expected_payload_sys_path)
        self.mock_util.fs.extract_tar.assert_called_once_with(expected_payload_sys_path, delete=True)

    def test_exception_is_raised_if_problem_occurs_writing_subjob(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        subjob = build.all_subjobs()[0]

        self.mock_util.fs.write_file.side_effect = FileExistsError

        with self.assertRaises(Exception):
            build.complete_subjob(subjob.subjob_id(), payload=self._FAKE_PAYLOAD)

    @genty_dataset(
        max_executors_reached=(1, False),
        max_executors_not_reached=(30, True),
    )
    def test_need_more_slaves_returns_false_if_and_only_if_max_executors_is_reached(
            self,
            max_executors_for_build,
            build_should_need_more_slaves
    ):
        job_config = self._create_job_config(max_executors=max_executors_for_build)
        build = self._create_test_build(BuildStatus.PREPARED, num_subjobs=100, job_config=job_config)

        mock_slave = self._create_mock_slave(num_executors=5)
        build.allocate_slave(slave=mock_slave)

        self.assertEqual(build.needs_more_slaves(), build_should_need_more_slaves,
                         'If and only if the maximum number of executors is allocated we should not need more slaves.')

    def test_build_cannot_be_prepared_more_than_once(self):
        build = self._create_test_build(BuildStatus.QUEUED)
        job_config = self._create_job_config()
        subjobs = self._create_subjobs(count=3, job_config=job_config)

        build.prepare(subjobs=subjobs, job_config=job_config)

        with self.assertRaisesRegex(RuntimeError, r'prepare\(\) was called more than once'):
            build.prepare(subjobs=subjobs, job_config=job_config)

    def test_teardown_called_on_slave_when_no_subjobs_remain(self):
        build = Build(BuildRequest({}))
        slave = Slave('', 1)
        slave.teardown = MagicMock()
        slave.free_executor = MagicMock(return_value=0)
        build._unstarted_subjobs = Queue()
        build._slaves_allocated = [slave]

        build.execute_next_subjob_or_teardown_slave(slave)

        slave.teardown.assert_called_with()

    def test_teardown_called_on_slave_when_slave_in_shutdown_mode(self):
        build = Build(BuildRequest({}))
        slave = Slave('', 1)
        slave.teardown = MagicMock()
        slave._is_in_shutdown_mode = True
        slave.free_executor = MagicMock(return_value=0)
        build._unstarted_subjobs = Queue()
        build._unstarted_subjobs.put(Mock(spec=Subjob))
        build._slaves_allocated = [slave]

        build.execute_next_subjob_or_teardown_slave(slave)

        slave.teardown.assert_called_with()

    def test_cancel_depletes_queue_and_sets_canceled(self):
        build = Build(BuildRequest({}))
        build._unstarted_subjobs = Queue()
        build._unstarted_subjobs.put(1)
        slave_mock = Mock()
        build._slaves_allocated = [slave_mock]

        build.cancel()

        self.assertTrue(build._is_canceled, "Build should've been canceled")
        self.assertTrue(build._unstarted_subjobs.empty(), "Build's unstarted subjobs should've been depleted")

    def test_cancel_exits_early_if_build_not_running(self):
        build = Build(BuildRequest({}))
        build._unstarted_subjobs = Queue()
        slave_mock = Mock()
        build._slaves_allocated = [slave_mock]
        build._status = Mock(return_value=BuildStatus.FINISHED)

        build.cancel()

        self.assertFalse(build._is_canceled, "Build should not be canceled")
        self.assertEqual(slave_mock.teardown.call_count, 0, "Teardown should not have been called")

    def test_validate_update_params_for_cancelling_build(self):
        build = Build(BuildRequest({}))

        success, response = build.validate_update_params({'status': 'canceled'})

        self.assertTrue(success, "Correct status update should report success")
        self.assertEqual({}, response, "Error response should be empty")

    def test_validate_update_params_rejects_bad_params(self):
        build = Build(BuildRequest({}))

        success, response = build.validate_update_params({'status': 'foo'})

        self.assertFalse(success, "Bad status update reported success")
        self.assertEqual({'error': "Value (foo) is not in list of allowed values (['canceled']) for status"}, response,
                         "Error response not expected")

    def test_validate_update_params_rejects_bad_keys(self):
        build = Build(BuildRequest({}))

        success, response = build.validate_update_params({'badkey': 'foo'})

        self.assertFalse(success, "Bad status update reported success")
        self.assertEqual({'error': "Key (badkey) is not in list of allowed keys (status)"}, response,
                         "Error response not expected")

    def test_update_state_to_canceled_sets_state_correctly(self):
        build = Build(BuildRequest({}))
        build._unstarted_subjobs = Queue()

        success = build.update_state({'status': 'canceled'})

        self.assertEqual(build._status(), BuildStatus.CANCELED, "Status not set to canceled")
        self.assertTrue(success, "Update did not report success")

    def test_execute_next_subjob_with_empty_queue_cant_teardown_same_slave_twice(self):
        build = Build(BuildRequest({}))
        build._unstarted_subjobs = Queue()
        slave = Mock()
        slave.free_executor = Mock(return_value=0)
        build._slaves_allocated.append(slave)

        build.execute_next_subjob_or_teardown_slave(slave)
        build.execute_next_subjob_or_teardown_slave(slave)

        self.assertEqual(slave.teardown.call_count, 1, "Teardown should only be called once")

    def test_allocate_slave_increments_by_num_executors_when_max_is_inf(self):
        build = Build(BuildRequest({}))
        slave = Mock()
        slave.num_executors = 10
        build.allocate_slave(slave)
        self.assertEqual(build._num_executors_allocated, 10, "Should be incremented by num executors")

    def test_allocate_slave_increments_by_per_slave_when_max_not_inf_and_less_than_num(self):
        build = Build(BuildRequest({}))
        build._max_executors_per_slave = 5
        slave = Mock()
        slave.num_executors = 10
        build.allocate_slave(slave)
        self.assertEqual(build._num_executors_allocated, 5, "Should be incremented by num executors")

    def test_generate_project_type_raises_error_if_failed_to_generate_project(self):
        build = Build(BuildRequest({}))
        self.patch('app.master.build.util.create_project_type').return_value = None

        with self.assertRaises(BuildProjectError):
            build.generate_project_type()

    def test_creating_build_sets_queued_timestamp(self):
        build = self._create_test_build()
        self.assertIsNotNone(build.get_state_timestamp(BuildStatus.QUEUED),
                             '"queued" timestamp should be set immediately after build creation.')

    def test_preparing_build_sets_prepared_timestamps(self):
        job_config = self._create_job_config()
        subjobs = self._create_subjobs(job_config=job_config)
        build = self._create_test_build(BuildStatus.QUEUED)

        self.assertIsNone(build.get_state_timestamp(BuildStatus.PREPARED),
                          '"prepared" timestamp should not be set before build preparation.')

        build.prepare(subjobs=subjobs, job_config=job_config)

        self.assertIsNotNone(build.get_state_timestamp(BuildStatus.PREPARED),
                             '"prepared" timestamp should not be set before build preparation.')

    def test_allocating_slave_to_build_sets_building_timestamp_only_on_first_slave_allocation(self):
        mock_slave1 = self._create_mock_slave()
        mock_slave2 = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.PREPARED)

        self.assertIsNone(build.get_state_timestamp(BuildStatus.BUILDING),
                          '"building" timestamp should not be set until slave allocated.')

        build.allocate_slave(slave=mock_slave1)
        building_timestamp1 = build.get_state_timestamp(BuildStatus.BUILDING)
        build.allocate_slave(slave=mock_slave2)
        building_timestamp2 = build.get_state_timestamp(BuildStatus.BUILDING)

        self.assertIsNotNone(building_timestamp1, '"building" timestamp should be set after first slave allocated.')
        self.assertEqual(building_timestamp1, building_timestamp2,
                         '"building" timestamp should not change upon further slave allocation.')

    def test_finishing_build_sets_finished_timestamp(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertIsNone(build.get_state_timestamp(BuildStatus.FINISHED),
                          '"finished" timestamp should not be set until build finishes.')

        self._finish_test_build(build)
        self.assertIsNotNone(build.get_state_timestamp(BuildStatus.FINISHED),
                             '"finished" timestamp should be set when build finishes.')

    def test_marking_build_failed_sets_error_timestamp(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertIsNone(build.get_state_timestamp(BuildStatus.ERROR),
                          '"error" timestamp should not be set unless build fails.')

        build.mark_failed('Test build was intentionally marked failed.')
        self.assertIsNotNone(build.get_state_timestamp(BuildStatus.ERROR),
                             '"error" timestamp should be set when build fails.')

    def test_canceling_build_sets_canceled_timestamp(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertIsNone(build.get_state_timestamp(BuildStatus.CANCELED),
                          '"canceled" timestamp should not be set unless build is canceled.')

        build.cancel()
        self.assertIsNotNone(build.get_state_timestamp(BuildStatus.CANCELED),
                             '"canceled" timestamp should be set when build is canceled.')

    def _create_test_build(self, build_status=None, job_config=None, num_subjobs=3, num_atoms_per_subjob=3):
        """
        Create a Build instance for testing purposes. The instance will be created and brought to the specified
        state similarly to how it would reach that state in actual app execution. Build instances have a huge
        amount of internal state with complicated interactions, so this helper method helps us write tests that
        are much more consistent and closer to reality. It also helps us avoid modifying a build's private members
        directly.

        :type build_status: BuildStatus
        :rtype: Build
        """
        build = Build(BuildRequest(build_parameters={}))
        if build_status is None:
            return build

        # QUEUED: Instantiate a mock project_type instance for the build.
        mock_project_type = self._create_mock_project_type()
        self.patch('app.master.build.util.create_project_type').return_value = mock_project_type
        build.generate_project_type()
        if build_status is BuildStatus.QUEUED:
            return build

        # PREPARED: Create a fake job config and subjobs and hand them off to the build.
        job_config = job_config or self._create_job_config()
        subjobs = self._create_subjobs(count=num_subjobs, num_atoms_each=num_atoms_per_subjob, job_config=job_config)
        build.prepare(subjobs=subjobs, job_config=job_config)
        if build_status is BuildStatus.PREPARED:
            return build

        # BUILDING: Allocate a slave and begin subjob executions on that slave.
        mock_slave = self._create_mock_slave()
        build.allocate_slave(slave=mock_slave)
        build.begin_subjob_executions_on_slave(slave=mock_slave)
        if build_status is BuildStatus.BUILDING:
            return build

        # ERROR: Mark the in-progress build as failed.
        if build_status is BuildStatus.ERROR:
            build.mark_failed(failure_reason='Test build was intentionally marked failed.')
            return build

        # CANCELED: Cancel the in-progress build.
        if build_status is BuildStatus.CANCELED:
            build.cancel()
            return build

        # FINISHED: Complete all subjobs and allow all postbuild tasks to execute.
        self._finish_test_build(build)
        if build_status is BuildStatus.FINISHED:
            return build

        raise ValueError('Unsupported value for build_status: "{}".'.format(build_status))

    def _create_subjobs(self, count=3, num_atoms_each=1, build_id=0, job_config=None):
        return [
            Subjob(
                build_id=build_id,
                subjob_id=i,
                project_type=None,
                job_config=job_config,
                atoms=[Atom('NAME', 'Leonardo') for _ in range(num_atoms_each)],
            )
            for i in range(count)
        ]

    def _create_job_config(
        self,
        max_executors=_FAKE_MAX_EXECUTORS,
        max_executors_per_slave=_FAKE_MAX_EXECUTORS_PER_SLAVE,
    ):
        atomizer = Atomizer([{'FAKE': 'fake atomizer command'}])
        return JobConfig('', '', '', '', atomizer, max_executors, max_executors_per_slave)

    def _create_mock_project_type(self):
        return MagicMock(spec_set=ProjectType())

    def _create_mock_slave(self, num_executors=5):
        mock = MagicMock(spec_set=Slave(slave_url=self._FAKE_SLAVE_URL, num_executors=num_executors))
        mock.url = self._FAKE_SLAVE_URL
        mock.num_executors = num_executors
        return mock

    def _finish_test_build(self, build):
        """
        Complete all the subjobs for a build, triggering the build's postbuild tasks and transitioning it
        to the "finished" state. Since postbuild tasks are asynchronous, this injects an event so we can
        detect when the asynchronous method is finished.
        :type build: Build
        """
        # Inject an event into the build's postbuild task so that we can detect when it completes.
        postbuild_tasks_complete_event = Event()
        self._on_async_postbuild_tasks_completed(build, postbuild_tasks_complete_event.set)

        # Complete all subjobs for this build.
        for subjob in build.all_subjobs():
            build.complete_subjob(subjob.subjob_id())

        # Wait for the async postbuild thread to complete executing postbuild tasks.
        self.assertTrue(postbuild_tasks_complete_event.wait(timeout=5), 'Postbuild tasks should complete quickly.')

    def _on_async_postbuild_tasks_completed(self, build, callback):
        # Patch a build so it executes the specified callback after its PostBuild thread finishes.
        original_async_postbuild_method = build._perform_async_postbuild_tasks

        def async_postbuild_tasks_with_callback():
            original_async_postbuild_method()
            callback()

        build._perform_async_postbuild_tasks = async_postbuild_tasks_with_callback
