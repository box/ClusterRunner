from queue import Queue
from os.path import abspath, join
import sys
from threading import Event
from unittest.mock import MagicMock, Mock, mock_open

from app.master.atom import Atom
from app.master.atomizer import Atomizer
from app.master.build import Build, BuildStatus, BuildProjectError
from app.master.build_request import BuildRequest
from app.master.job_config import JobConfig
from app.master.slave import Slave
from app.master.subjob import Subjob
from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestBuild(BaseUnitTestCase):

    _FAKE_SLAVE_URL = 'my.favorite.slave.com:40001'
    _FAKE_MAX_EXECUTORS = sys.maxsize
    _FAKE_MAX_EXECUTORS_PER_SLAVE = sys.maxsize

    def setUp(self):
        super().setUp()
        mock_util = self.patch('app.master.build.app.util')  # stub out util since these often interact with the fs
        self.mock_fs = mock_util.fs

    def test_allocate_slave_calls_slave_setup(self):
        subjobs = self._create_subjobs()
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave()
        build = Build(Mock(spec_set=BuildRequest))
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config())
        build.allocate_slave(mock_slave)

        mock_slave.setup.assert_called_once_with(build)

    def test_build_doesnt_use_more_than_max_executors(self):
        subjobs = self._create_subjobs()
        mock_project_type = self._create_mock_project_type()
        fake_setup_command = 'mock command'
        mock_slaves = [self._create_mock_slave(num_executors=5) for _ in range(3)]
        expected_num_executors = 12  # We expect the build to use 12 out of 15 available executors.

        build = Build(BuildRequest({'setup': fake_setup_command}))
        build._project_type = mock_project_type
        build.execute_next_subjob_or_teardown_slave = MagicMock()

        build.prepare(subjobs, self._create_job_config(max_executors=expected_num_executors))
        [build.allocate_slave(mock_slave) for mock_slave in mock_slaves]
        [build.begin_subjob_executions_on_slave(mock_slave) for mock_slave in mock_slaves]

        self.assertEqual(build.execute_next_subjob_or_teardown_slave.call_count, expected_num_executors,
                         'Build should start executing as many subjobs as its max_executors setting.')

    def test_build_doesnt_use_more_than_max_executors_per_slave(self):
        subjobs = self._create_subjobs()
        mock_project_type = self._create_mock_project_type()
        fake_setup_command = 'mock command'
        mock_slaves = [self._create_mock_slave(num_executors=5) for _ in range(3)]
        max_executors_per_slave = 2
        expected_total_num_executors_used = 6  # We expect the build to use 2 executors on each of the 3 slaves.

        build = Build(BuildRequest({'setup': fake_setup_command}))
        build._project_type = mock_project_type
        build.execute_next_subjob_or_teardown_slave = MagicMock()

        build.prepare(subjobs, self._create_job_config(max_executors_per_slave=max_executors_per_slave))
        [build.allocate_slave(mock_slave) for mock_slave in mock_slaves]

        expected_current_num_executors_used = 0
        for i in range(len(mock_slaves)):
            build.begin_subjob_executions_on_slave(mock_slaves[i])
            expected_current_num_executors_used += max_executors_per_slave
            self.assertEqual(
                build.execute_next_subjob_or_teardown_slave.call_count, expected_current_num_executors_used,
                'After allocating {} slaves, build with max_executors_per_slave set to {} should only be using {} '
                'executors.'.format(i + 1, max_executors_per_slave, expected_current_num_executors_used))

        self.assertEqual(
            build.execute_next_subjob_or_teardown_slave.call_count, expected_total_num_executors_used,
            'Build should start executing as many subjobs per slave as its max_executors_per_slave setting.')

    def test_build_status_returns_requested_after_build_creation(self):
        build = Build(BuildRequest({}))
        status = build._status()

        self.assertEqual(status, BuildStatus.QUEUED,
                         'Build status should be QUEUED immediately after build has been created.')

    def test_build_status_returns_queued_after_build_preparation(self):
        subjobs = self._create_subjobs()
        mock_project_type = self._create_mock_project_type()
        build = Build(BuildRequest({}))
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config())
        status = build._status()

        self.assertEqual(status, BuildStatus.QUEUED,
                         'Build status should be QUEUED after build has been prepared.')

    def test_build_status_returns_building_after_setup_has_started(self):
        subjobs = self._create_subjobs()
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave()
        build = Build(BuildRequest({}))
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config())
        build.allocate_slave(mock_slave)

        self.assertEqual(build._status(), BuildStatus.BUILDING,
                         'Build status should be BUILDING after setup has started on slaves.')

    def test_build_status_returns_building_after_setup_is_complete_and_subjobs_are_executing(self):
        subjobs = self._create_subjobs(count=3)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=2)
        build = Build(BuildRequest({}))
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config())
        build.allocate_slave(mock_slave)
        build.begin_subjob_executions_on_slave(mock_slave)  # two out of three subjobs are now in progress

        self.assertEqual(build._status(), BuildStatus.BUILDING,
                         'Build status should be BUILDING after subjobs have started executing on slaves.')

    def test_build_status_returns_finished_after_all_subjobs_complete_and_slaves_finished(self):
        subjobs = self._create_subjobs(count=3)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=3)
        postbuild_tasks_complete_event = Event()
        build = Build(BuildRequest({}))
        build._project_type = mock_project_type
        build._create_build_artifact = MagicMock()
        self._on_async_postbuild_tasks_completed(build, postbuild_tasks_complete_event.set)

        build.prepare(subjobs, self._create_job_config())
        build.allocate_slave(mock_slave)  # all three subjobs are now "in progress"
        for subjob in subjobs:
            build.complete_subjob(subjob.subjob_id())

        # Wait for the async thread to complete executing postbuild tasks.
        self.assertTrue(postbuild_tasks_complete_event.wait(timeout=2), 'Postbuild tasks should complete within a few'
                                                                        'seconds.')
        # Verify build artifacts was called after subjobs completed
        build._create_build_artifact.assert_called_once_with()
        self.assertTrue(build._subjobs_are_finished)
        self.assertEqual(build._status(), BuildStatus.FINISHED)

    def test_complete_subjob_parses_payload_and_stores_value_in_atom_objects(self):
        m_open = self.patch('app.master.build.open', new=mock_open(read_data='1'), create=True)
        Configuration['results_directory'] = abspath(join('some', 'temp', 'directory'))
        build = Build(BuildRequest({}))
        build._project_type = self._create_mock_project_type()
        subjob = self._create_subjobs(count=1, build_id=build.build_id(), atoms=[Atom('FOO', 1)])[0]
        build.prepare([subjob], self._create_job_config())

        payload = {'filename': 'turtles.txt', 'body': 'Heroes in a half shell.'}
        build.complete_subjob(subjob.subjob_id(), payload=payload)

        expected_payload_sys_path = join(Configuration['results_directory'], '1', 'artifact_0_0')
        m_open.assert_called_once_with(
            join(expected_payload_sys_path, Subjob.EXIT_CODE_FILE),
            'r',
        )
        self.assertEqual(subjob.atoms[0].exit_code, 1)

    def test_complete_subjob_writes_and_extracts_payload_to_correct_directory(self):
        Configuration['results_directory'] = abspath(join('some', 'temp', 'directory'))
        build = Build(BuildRequest({}))
        build._project_type = self._create_mock_project_type()
        subjob = self._create_subjobs(count=1, build_id=build.build_id())[0]
        build.prepare([subjob], self._create_job_config())

        payload = {'filename': 'turtles.txt', 'body': 'Heroes in a half shell.'}
        build.complete_subjob(subjob.subjob_id(), payload=payload)

        expected_payload_sys_path = join(Configuration['results_directory'], '1', 'turtles.txt')
        self.mock_fs.write_file.assert_called_once_with('Heroes in a half shell.', expected_payload_sys_path)
        self.mock_fs.extract_tar.assert_called_once_with(expected_payload_sys_path, delete=True)

    def test_exception_is_raised_if_problem_occurs_writing_subjob(self):
        Configuration['results_directory'] = abspath(join('some', 'temp', 'directory'))
        build = Build(BuildRequest({}))
        build._project_type = self._create_mock_project_type()
        subjob = self._create_subjobs(count=1, build_id=build.build_id())[0]
        build.prepare([subjob], self._create_job_config())
        self.mock_fs.write_file.side_effect = FileExistsError

        with self.assertRaises(Exception):
            payload = {'filename': 'turtles.txt', 'body': 'Heroes in a half shell.'}
            build.complete_subjob(subjob.subjob_id(), payload=payload)

    def test_need_more_slaves_returns_false_if_max_processes_is_reached(self):
        subjobs = self._create_subjobs(count=5)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=1)
        build = Build(BuildRequest({}))
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config(max_executors=1))
        build.allocate_slave(mock_slave)
        self.assertFalse(build.needs_more_slaves(), "if max processes is reached, we shouldn't need more slaves")

    def test_need_more_slaves_returns_true_if_max_processes_is_not_reached(self):
        subjobs = self._create_subjobs(count=8)
        mock_project_type = self._create_mock_project_type()
        mock_slave = self._create_mock_slave(num_executors=5)
        build = Build(BuildRequest({}))
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config(max_executors=8))
        build.allocate_slave(mock_slave)
        self.assertTrue(build.needs_more_slaves(), "if max_processes is not reached, we should need more slaves")

    def test_build_cannot_be_prepared_more_than_once(self):
        build = Build(BuildRequest({}))
        subjobs = self._create_subjobs(count=3)
        mock_project_type = self._create_mock_project_type()
        build._project_type = mock_project_type

        build.prepare(subjobs, self._create_job_config())

        with self.assertRaises(Exception):
            build.prepare(subjobs, mock_project_type, self._create_job_config())

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

    def _create_subjobs(self, count=3, build_id=0, atoms=None):
        return [
            Subjob(
                build_id=build_id,
                subjob_id=i,
                project_type=None,
                job_config=None,
                atoms=atoms if atoms else [],
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

    def _on_async_postbuild_tasks_completed(self, build, callback):
        # Patch a build so it executes the specified callback after its PostBuild thread finishes.
        original_async_postbuild_method = build._perform_async_postbuild_tasks

        def async_postbuild_tasks_with_callback():
            original_async_postbuild_method()
            callback()

        build._perform_async_postbuild_tasks = async_postbuild_tasks_with_callback
