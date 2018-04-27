from unittest.mock import Mock

from app.manager.build import Build
from app.manager.build_scheduler_pool import BuildSchedulerPool
from app.manager.worker import Worker
from app.manager.worker_allocator import WorkerAllocator
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestWorkerAllocator(BaseUnitTestCase):

    def test_start_should_raise_if_allocation_thread_is_dead(self):
        worker_allocator = self._create_worker_allocator()
        worker_allocator._allocation_thread.is_alive = Mock(return_value=True)

        self.assertRaises(RuntimeError, worker_allocator.start)

    def test_start_should_start_allocation_loop(self):
        worker_allocator = self._create_worker_allocator()
        worker_allocator._allocation_thread.is_alive = Mock(return_value=False)
        worker_allocator._allocation_thread.start = Mock()

        worker_allocator.start()

        assert worker_allocator._allocation_thread.start.called

    def test_worker_allocation_loop_should_allocate_a_worker(self):
        mock_build = Mock(spec=Build, needs_more_workers=Mock(return_value=True),
                          allocate_worker=Mock(side_effect=AbortLoopForTesting))
        mock_worker = Mock(spec=Worker, url='', is_alive=Mock(return_value=True), is_shutdown=Mock(return_value=False))
        worker_allocator = self._create_worker_allocator()
        worker_allocator._scheduler_pool.next_prepared_build_scheduler = Mock(return_value=mock_build)
        worker_allocator._idle_workers.get = Mock(return_value=mock_worker)

        self.assertRaises(AbortLoopForTesting, worker_allocator._worker_allocation_loop)

    def test_worker_allocation_loop_should_return_idle_worker_to_queue_if_not_needed(self):
        mock_build = Mock(spec=Build, needs_more_workers=Mock(side_effect=[True, False]))
        mock_worker = Mock(spec=Worker, url='', is_alive=Mock(return_value=True), is_shutdown=Mock(return_value=False))
        worker_allocator = self._create_worker_allocator()
        worker_allocator._scheduler_pool.next_prepared_build_scheduler = Mock(return_value=mock_build)
        worker_allocator._idle_workers.get = Mock(return_value=mock_worker)
        worker_allocator.add_idle_worker = Mock(side_effect=AbortLoopForTesting)

        self.assertRaises(AbortLoopForTesting, worker_allocator._worker_allocation_loop)

    def test_add_idle_worker_should_mark_worker_idle_and_add_to_queue(self):
        mock_worker = Mock(spec=Worker, url='', mark_as_idle=Mock())
        worker_allocator = self._create_worker_allocator()
        worker_allocator._idle_workers.put = Mock()

        worker_allocator.add_idle_worker(mock_worker)

        self.assertTrue(mock_worker.mark_as_idle.called)
        worker_allocator._idle_workers.put.assert_called_with(mock_worker)

    def test_add_idle_worker_should_not_add_worker_to_queue_if_worker_is_shutdown(self):
        mock_worker = Worker('', 10)
        mock_worker.kill = Mock(return_value=None)
        mock_worker.set_shutdown_mode()
        worker_allocator = self._create_worker_allocator()
        worker_allocator._idle_workers.put = Mock()

        worker_allocator.add_idle_worker(mock_worker)

        self.assertFalse(worker_allocator._idle_workers.put.called)

    def _create_worker_allocator(self, **kwargs):
        """
        Create a worker allocator for testing.
        :param kwargs: Any constructor parameters for the worker; if none are specified, test defaults will be used.
        :rtype: WorkerAllocator
        """
        return WorkerAllocator(Mock(spec_set=BuildSchedulerPool))

class AbortLoopForTesting(Exception):
    """
    An error we can raise to stop the while True loop in worker allocation
    """
