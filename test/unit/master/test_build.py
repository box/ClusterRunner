from os.path import abspath, join
import sys
from threading import Event
from unittest import skip
from unittest.mock import MagicMock, Mock, mock_open, call

from genty import genty, genty_dataset

from app.master.atom import Atom, AtomState
from app.master.atomizer import Atomizer
from app.master.build import Build, BuildStatus, BuildProjectError
from app.master.build_artifact import BuildArtifact
from app.master.build_fsm import BuildState
from app.master.build_request import BuildRequest
from app.master.build_scheduler_pool import BuildSchedulerPool
from app.master.job_config import JobConfig
from app.master.slave import Slave, SlaveMarkedForShutdownError
from app.master.subjob import Subjob
from app.master.subjob_calculator import SubjobCalculator
from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration
from app.util.counter import Counter
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
        self.mock_listdir = self.patch('os.listdir')
        self.scheduler_pool = BuildSchedulerPool()

    def test_allocate_slave_calls_slave_setup(self):
        mock_slave = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.PREPARED)
        scheduler = self.scheduler_pool.get(build)

        scheduler.allocate_slave(mock_slave)

        mock_slave.setup.assert_called_once_with(build, executor_start_index=0)

    def test_build_doesnt_use_more_than_max_executors(self):
        mock_slaves = [self._create_mock_slave(num_executors=5) for _ in range(3)]  # 15 total available executors
        expected_num_executors_used = 12  # We expect the build to use 12 out of 15 available executors.
        job_config = self._create_job_config(max_executors=expected_num_executors_used)
        build = self._create_test_build(BuildStatus.PREPARED, job_config=job_config)
        scheduler = self.scheduler_pool.get(build)
        scheduler.execute_next_subjob_or_free_executor = Mock()

        for mock_slave in mock_slaves:
            scheduler.allocate_slave(mock_slave)
            scheduler.begin_subjob_executions_on_slave(mock_slave)

        self.assertEqual(scheduler.execute_next_subjob_or_free_executor.call_count, expected_num_executors_used,
                         'Build should start executing as many subjobs as its max_executors setting.')

    def test_build_doesnt_use_more_than_max_executors_per_slave(self):
        mock_slaves = [self._create_mock_slave(num_executors=5) for _ in range(3)]
        max_executors_per_slave = 2
        job_config = self._create_job_config(max_executors_per_slave=max_executors_per_slave)
        build = self._create_test_build(build_status=BuildStatus.PREPARED, job_config=job_config)
        scheduler = self.scheduler_pool.get(build)
        scheduler.execute_next_subjob_or_free_executor = Mock()

        for mock_slave in mock_slaves:
            scheduler.allocate_slave(mock_slave)
            scheduler.begin_subjob_executions_on_slave(mock_slave)

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
            scheduler.execute_next_subjob_or_free_executor.mock_calls,
            expected_subjob_execution_calls,
            'Build should start executing as many subjobs per slave as its max_executors_per_slave setting.')

    def test_build_status_returns_queued_after_build_creation(self):
        build = self._create_test_build()

        self.assertEqual(build._status(), BuildStatus.QUEUED,
                         'Build status should be QUEUED immediately after build has been created.')

    @skip('PREPARING not yet supported in _create_test_build()')  # WIP(joey): Support PREPARING state.
    def test_build_status_returns_preparing_after_build_begins_prep(self):
        build = self._create_test_build(BuildState.PREPARING)

        self.assertEqual(build._status(), BuildState.PREPARING,
                         'Build status should be PREPARING after build has begun preparation.')

    def test_build_status_returns_prepared_after_build_preparation(self):
        build = self._create_test_build(BuildStatus.PREPARED)

        self.assertEqual(build._status(), BuildStatus.PREPARED,
                         'Build status should be PREPARED after build has been prepared.')

    def test_build_status_returns_building_after_first_subjob_has_been_executed(self):
        mock_slave = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.PREPARED)
        scheduler = self.scheduler_pool.get(build)
        scheduler.allocate_slave(mock_slave)
        scheduler.execute_next_subjob_or_free_executor(mock_slave)

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
        self.assertTrue(build._all_subjobs_are_finished())
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
        max_executors_reached=(1, False, 100),
        max_executors_not_reached=(30, True, 100),
        fewer_subjobs_than_max_executors=(30, False, 1),
    )
    def test_need_more_slaves(
            self,
            max_executors_for_build,
            build_should_need_more_slaves,
            num_subjobs
    ):
        job_config = self._create_job_config(max_executors=max_executors_for_build)
        build = self._create_test_build(BuildStatus.PREPARED, num_subjobs=num_subjobs, job_config=job_config)
        scheduler = self.scheduler_pool.get(build)

        mock_slave = self._create_mock_slave(num_executors=5)
        scheduler.allocate_slave(slave=mock_slave)

        self.assertEqual(scheduler.needs_more_slaves(), build_should_need_more_slaves,
                         'If and only if the maximum number of executors is allocated we should not need more slaves.')

    def test_build_cannot_be_prepared_more_than_once(self):
        build = self._create_test_build(BuildStatus.QUEUED)
        job_config = self._create_job_config()
        subjobs = self._create_subjobs(count=3, job_config=job_config)
        subjob_calculator = self._create_mock_subjob_calc(subjobs)

        build.prepare(subjob_calculator)

        with self.assertRaisesRegex(RuntimeError, r'prepare\(\) was called more than once'):
            build.prepare(subjob_calculator)

    def test_teardown_called_on_slave_when_no_subjobs_remain(self):
        mock_slave = self._create_mock_slave(num_executors=1)
        self._create_test_build(BuildStatus.FINISHED, num_subjobs=1, slaves=[mock_slave])

        mock_slave.teardown.assert_called_with()

    def test_teardown_called_on_all_slaves_when_no_subjobs_remain(self):
        mock_slaves = [
            self._create_mock_slave(num_executors=5),
            self._create_mock_slave(num_executors=4),
            self._create_mock_slave(num_executors=3),
        ]
        self._create_test_build(BuildStatus.FINISHED, num_subjobs=20, slaves=mock_slaves)

        for mock_slave in mock_slaves:
            mock_slave.teardown.assert_called_with()

    def test_teardown_called_on_slave_when_slave_in_shutdown_mode(self):
        mock_slave = self._create_mock_slave(num_executors=5)
        mock_slave.start_subjob.side_effect = SlaveMarkedForShutdownError

        self._create_test_build(BuildStatus.BUILDING, num_subjobs=30, slaves=[mock_slave])

        mock_slave.teardown.assert_called_with()

    def test_cancel_prevents_further_subjob_starts_and_sets_canceled(self):  # dev: this is flaky now
        mock_slave = self._create_mock_slave(num_executors=5)
        build = self._create_test_build(BuildStatus.BUILDING, num_subjobs=30, slaves=[mock_slave])

        self.assertEqual(mock_slave.start_subjob.call_count, 5, 'Slave should only have had as many subjobs started '
                                                                'as its num_executors.')
        build.cancel()
        self._finish_test_build(build, assert_postbuild_tasks_complete=False)

        self.assertEqual(build._status(), BuildStatus.CANCELED, 'Canceled build should have canceled state.')
        self.assertEqual(mock_slave.start_subjob.call_count, 5, 'A canceled build should not have any more subjobs '
                                                                'started after it has been canceled.')

    def test_cancel_is_a_noop_if_build_is_already_finished(self):
        mock_slave = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.FINISHED, slaves=[mock_slave])
        num_slave_calls_before_cancel = len(mock_slave.method_calls)

        build.cancel()

        self.assertEqual(build._status(), BuildStatus.FINISHED,
                         'Canceling a finished build should not change its state.')
        self.assertEqual(len(mock_slave.method_calls), num_slave_calls_before_cancel,
                         'Canceling a finished build should not cause any further calls to slave.')

    def test_validate_update_params_for_cancelling_build(self):
        build = self._create_test_build()

        success, response = build.validate_update_params({'status': 'canceled'})

        self.assertTrue(success, "Correct status update should report success")
        self.assertEqual({}, response, "Error response should be empty")

    def test_validate_update_params_rejects_bad_params(self):
        build = self._create_test_build()

        success, response = build.validate_update_params({'status': 'foo'})

        self.assertFalse(success, "Bad status update reported success")
        self.assertEqual({'error': "Value (foo) is not in list of allowed values (['canceled']) for status"}, response,
                         "Error response not expected")

    def test_validate_update_params_rejects_bad_keys(self):
        build = self._create_test_build()

        success, response = build.validate_update_params({'badkey': 'canceled'})

        self.assertFalse(success, "Bad status update reported success")
        self.assertEqual({'error': "Key (badkey) is not in list of allowed keys (status)"}, response,
                         "Error response not expected")

    def test_update_state_to_canceled_will_cancel_build(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        build.cancel = Mock()

        success = build.update_state({'status': 'canceled'})

        build.cancel.assert_called_once_with()
        self.assertTrue(success, "Update did not report success")

    def test_execute_next_subjob_with_no_more_subjobs_should_not_teardown_same_slave_twice(self):
        mock_slave = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.BUILDING, slaves=[mock_slave])
        scheduler = self.scheduler_pool.get(build)
        self._finish_test_build(build, assert_postbuild_tasks_complete=False)

        scheduler.execute_next_subjob_or_free_executor(mock_slave)
        scheduler.execute_next_subjob_or_free_executor(mock_slave)

        self.assertEqual(mock_slave.teardown.call_count, 1, "Teardown should only be called once")

    def test_slave_is_fully_allocated_when_max_executors_per_slave_is_not_set(self):
        mock_slave = self._create_mock_slave(num_executors=10)
        job_config = self._create_job_config(max_executors_per_slave=float('inf'))
        self._create_test_build(BuildStatus.BUILDING, job_config=job_config, slaves=[mock_slave])

        self.assertEqual(mock_slave.claim_executor.call_count, 10, 'Claim executor should be called once for each '
                                                                   'of the slave executors.')

    def test_slave_is_only_allocated_up_to_max_executors_per_slave_setting(self):
        mock_slave = self._create_mock_slave(num_executors=10)
        job_config = self._create_job_config(max_executors_per_slave=5)
        self._create_test_build(BuildStatus.BUILDING, job_config=job_config, slaves=[mock_slave])

        self.assertEqual(mock_slave.claim_executor.call_count, 5, 'Claim executor should be called '
                                                                  'max_executors_per_slave times.')

    def test_generate_project_type_raises_error_if_failed_to_generate_project(self):
        build = self._create_test_build()
        self.patch('app.master.build.util.create_project_type').return_value = None

        with self.assertRaises(BuildProjectError):
            build.generate_project_type()

    def test_creating_build_sets_queued_timestamp(self):
        build = self._create_test_build()
        self.assertIsNotNone(self._get_build_state_timestamp(build, BuildState.QUEUED),
                             '"queued" timestamp should be set immediately after build creation.')

    def test_preparing_build_sets_prepared_timestamps(self):
        job_config = self._create_job_config()
        subjobs = self._create_subjobs(job_config=job_config)
        subjob_calculator = self._create_mock_subjob_calc(subjobs)
        build = self._create_test_build(BuildStatus.QUEUED)

        self.assertIsNone(self._get_build_state_timestamp(build, BuildState.PREPARED),
                          '"prepared" timestamp should not be set before build preparation.')

        build.prepare(subjob_calculator)

        self.assertIsNotNone(self._get_build_state_timestamp(build, BuildState.PREPARED),
                             '"prepared" timestamp should not be set before build preparation.')

    def test_preparing_build_creates_empty_results_directory(self):
        subjob_calculator = self._create_mock_subjob_calc([])
        build = self._create_test_build(BuildStatus.QUEUED)

        build.prepare(subjob_calculator)

        self.mock_util.fs.create_dir.assert_called_once_with(build._build_results_dir())

    def test_execute_next_subjob_or_free_executor_sets_building_timestamp_only_on_first_execution(self):
        mock_slave1 = self._create_mock_slave()
        build = self._create_test_build(BuildStatus.PREPARED)
        scheduler = self.scheduler_pool.get(build)
        scheduler.allocate_slave(slave=mock_slave1)

        self.assertIsNone(self._get_build_state_timestamp(build, BuildState.BUILDING),
                          '"building" timestamp should not be set until slave allocated.')

        scheduler.execute_next_subjob_or_free_executor(mock_slave1)
        building_timestamp1 = self._get_build_state_timestamp(build, BuildState.BUILDING)
        scheduler.execute_next_subjob_or_free_executor(mock_slave1)
        building_timestamp2 = self._get_build_state_timestamp(build, BuildState.BUILDING)
        self.assertIsNotNone(building_timestamp1, '"building" timestamp should be set after first subjob is started.')
        self.assertEqual(building_timestamp1, building_timestamp2,
                         '"building" timestamp should not change upon further subjob execution.')

    def test_finishing_build_sets_finished_timestamp(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertIsNone(self._get_build_state_timestamp(build, BuildState.FINISHED),
                          '"finished" timestamp should not be set until build finishes.')

        self._finish_test_build(build)
        self.assertIsNotNone(self._get_build_state_timestamp(build, BuildState.FINISHED),
                             '"finished" timestamp should be set when build finishes.')

    def test_marking_build_failed_sets_error_timestamp(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertIsNone(self._get_build_state_timestamp(build, BuildState.ERROR),
                          '"error" timestamp should not be set unless build fails.')

        build.mark_failed('Test build was intentionally marked failed.')
        self.assertIsNotNone(self._get_build_state_timestamp(build, BuildState.ERROR),
                             '"error" timestamp should be set when build fails.')

    def test_canceling_build_sets_canceled_timestamp(self):
        build = self._create_test_build(BuildStatus.BUILDING)

        self.assertIsNone(self._get_build_state_timestamp(build, BuildState.CANCELED),
                          '"canceled" timestamp should not be set unless build is canceled.')

        build.cancel()
        self.assertIsNotNone(self._get_build_state_timestamp(build, BuildState.CANCELED),
                             '"canceled" timestamp should be set when build is canceled.')

    def test_get_failed_atoms_returns_none_if_not_finished(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        self.assertIsNone(build._get_failed_atoms())

    def test_get_failed_atoms_returns_empty_list_if_finished_and_all_passed(self):
        build = self._create_test_build(BuildStatus.FINISHED)
        build._build_artifact = MagicMock(spec_set=BuildArtifact)
        build._build_artifact.get_failed_subjob_and_atom_ids.return_value = []

        self.assertEquals([], build._get_failed_atoms())

    def test_get_failed_atoms_returns_failed_atoms_only(self):
        build = self._create_test_build(BuildStatus.FINISHED, num_subjobs=5, num_atoms_per_subjob=10)
        build._build_artifact = MagicMock(spec_set=BuildArtifact)
        # Failed items: (SubjobId: 1, AtomId: 1) and (SubjobId: 3, AtomId: 3)
        build._build_artifact.get_failed_subjob_and_atom_ids.return_value = [(1, 1), (3, 3)]

        failed_atoms = build._get_failed_atoms()
        self.assertEquals(failed_atoms, [
            build._all_subjobs_by_id[1]._atoms[1],
            build._all_subjobs_by_id[3]._atoms[3],
        ])

    def test_delete_temporary_build_artifact_files_skips_results_tarball(self):
        build = self._create_test_build(BuildStatus.BUILDING)
        self.mock_listdir.return_value = ['some_dir1', BuildArtifact.ARTIFACT_FILE_NAME]
        expected_async_delete_call_path = join(build._build_results_dir(), 'some_dir1')
        self.patch('os.path.isdir').return_value = True
        mock_shutil = self.patch('app.master.build.shutil')

        build._delete_temporary_build_artifact_files()

        mock_shutil.rmtree.assert_called_once_with(expected_async_delete_call_path, ignore_errors=True)

    def _create_test_build(
            self,
            build_status=None,
            job_config=None,
            num_subjobs=3,
            num_atoms_per_subjob=3,
            slaves=None,
    ):
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
        mock_project_type.job_config.return_value = job_config
        subjobs = self._create_subjobs(count=num_subjobs, num_atoms_each=num_atoms_per_subjob, job_config=job_config)
        subjob_calculator = self._create_mock_subjob_calc(subjobs)
        build.prepare(subjob_calculator)
        if build_status is BuildStatus.PREPARED:
            return build

        # BUILDING: Allocate a slave and begin subjob executions on that slave.
        slaves = slaves or [self._create_mock_slave()]
        scheduler = self.scheduler_pool.get(build)
        for slave in slaves:
            scheduler.allocate_slave(slave=slave)
            scheduler.begin_subjob_executions_on_slave(slave=slave)
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
                atoms=[Atom('NAME=Leonardo') for _ in range(num_atoms_each)],
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
        """
        :type num_executors: int
        :rtype: Slave | MagicMock
        """
        slave_spec = Slave('', 0)  # constructor values don't matter since this is just a spec object
        mock_slave = MagicMock(spec_set=slave_spec, url=self._FAKE_SLAVE_URL, num_executors=num_executors)

        counter = Counter()
        mock_slave.claim_executor.side_effect = counter.increment
        mock_slave.free_executor.side_effect = counter.decrement

        return mock_slave

    def _create_mock_subjob_calc(self, subjobs):
        """
        :type subjobs: list[Subjob]
        :rtype: SubjobCalculator
        """
        mock_subjob_calculator = MagicMock(spec_set=SubjobCalculator)
        mock_subjob_calculator.compute_subjobs_for_build.return_value = subjobs
        return mock_subjob_calculator

    def _finish_test_build(self, build, assert_postbuild_tasks_complete=True):
        """
        Complete all the subjobs for a build, triggering the build's postbuild tasks and transitioning it
        to the "finished" state. Since postbuild tasks are asynchronous, this injects an event so we can
        detect when the asynchronous method is finished.
        :type build: Build
        :type assert_postbuild_tasks_complete: bool
        """
        build_scheduler = self.scheduler_pool.get(build)

        # Inject an event into the build's postbuild task so that we can detect when it completes.
        postbuild_tasks_complete_event = Event()
        self._on_async_postbuild_tasks_completed(build, postbuild_tasks_complete_event.set)

        # Complete all subjobs for this build.
        build_has_running_subjobs = True
        while build_has_running_subjobs:
            build_has_running_subjobs = False

            # copy allocated_slaves list since slaves may get deallocated during loop
            slaves_allocated = build_scheduler._slaves_allocated.copy()
            for mock_slave in slaves_allocated:
                self.assertIsInstance(mock_slave, Mock,
                                      '_finish_test_build() can only be used on builds with mock slaves.')

                for subjob in self._get_in_progress_subjobs_for_mock_slave(mock_slave):
                    build_has_running_subjobs = True
                    build.complete_subjob(subjob.subjob_id())
                    build_scheduler.execute_next_subjob_or_free_executor(mock_slave)

        # Wait for the async postbuild thread to complete executing postbuild tasks.
        if assert_postbuild_tasks_complete:
            self.assertTrue(postbuild_tasks_complete_event.wait(timeout=5),
                            'Postbuild tasks should be run and complete quickly when build finishes.')

    def _get_in_progress_subjobs_for_mock_slave(self, mock_slave):
        return [
            start_subjob_args[0]
            for start_subjob_args, _ in mock_slave.start_subjob.call_args_list
            if start_subjob_args[0].atoms[0].state is AtomState.IN_PROGRESS
        ]

    def _on_async_postbuild_tasks_completed(self, build, callback):
        # Patch a build so it executes the specified callback after its PostBuild thread finishes.
        original_async_postbuild_method = build._perform_async_postbuild_tasks

        def async_postbuild_tasks_with_callback():
            original_async_postbuild_method()
            callback()

        build._perform_async_postbuild_tasks = async_postbuild_tasks_with_callback

    def _get_build_state_timestamp(self, build, build_state):
        """
        Get the recorded timestamp for a given build status. This may be None if the build has
        not yet reached the specified state.
        :type build: Build
        :type build_state: BuildState
        :rtype: float | None
        """
        return build.api_representation()['state_timestamps'].get(build_state.lower())
