from unittest.mock import Mock

from app.master.build import Build
from app.master.build_scheduler_pool import BuildSchedulerPool
from app.master.slave import Slave
from app.master.slave_allocator import SlaveAllocator
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSlaveAllocator(BaseUnitTestCase):

    def test_start_should_raise_if_allocation_thread_is_dead(self):
        slave_allocator = self._create_slave_allocator()
        slave_allocator._allocation_thread.is_alive = Mock(return_value=True)

        self.assertRaises(RuntimeError, slave_allocator.start)

    def test_start_should_start_allocation_loop(self):
        slave_allocator = self._create_slave_allocator()
        slave_allocator._allocation_thread.is_alive = Mock(return_value=False)
        slave_allocator._allocation_thread.start = Mock()

        slave_allocator.start()

        assert slave_allocator._allocation_thread.start.called

    def test_slave_allocation_loop_should_allocate_a_slave(self):
        mock_build = Mock(spec=Build, needs_more_slaves=Mock(return_value=True),
                          allocate_slave=Mock(side_effect=AbortLoopForTesting))
        mock_slave = Mock(spec=Slave, url='', is_alive=Mock(return_value=True), is_shutdown=Mock(return_value=False))
        slave_allocator = self._create_slave_allocator()
        slave_allocator._scheduler_pool.next_prepared_build_scheduler = Mock(return_value=mock_build)
        slave_allocator._idle_slaves.get = Mock(return_value=mock_slave)

        self.assertRaises(AbortLoopForTesting, slave_allocator._slave_allocation_loop)

    def test_slave_allocation_loop_should_return_idle_slave_to_queue_if_not_needed(self):
        mock_build = Mock(spec=Build, needs_more_slaves=Mock(side_effect=[True, False]))
        mock_slave = Mock(spec=Slave, url='', is_alive=Mock(return_value=True), is_shutdown=Mock(return_value=False))
        slave_allocator = self._create_slave_allocator()
        slave_allocator._scheduler_pool.next_prepared_build_scheduler = Mock(return_value=mock_build)
        slave_allocator._idle_slaves.get = Mock(return_value=mock_slave)
        slave_allocator.add_idle_slave = Mock(side_effect=AbortLoopForTesting)

        self.assertRaises(AbortLoopForTesting, slave_allocator._slave_allocation_loop)

    def test_add_idle_slave_should_mark_slave_idle_and_add_to_queue(self):
        mock_slave = Mock(spec=Slave, url='', mark_as_idle=Mock())
        slave_allocator = self._create_slave_allocator()
        slave_allocator._idle_slaves.put = Mock()

        slave_allocator.add_idle_slave(mock_slave)

        self.assertTrue(mock_slave.mark_as_idle.called)
        slave_allocator._idle_slaves.put.assert_called_with(mock_slave)

    def test_add_idle_slave_should_not_add_slave_to_queue_if_slave_is_shutdown(self):
        mock_slave = Slave('', 10)
        mock_slave.kill = Mock(return_value=None)
        mock_slave.set_shutdown_mode()
        slave_allocator = self._create_slave_allocator()
        slave_allocator._idle_slaves.put = Mock()

        slave_allocator.add_idle_slave(mock_slave)

        self.assertFalse(slave_allocator._idle_slaves.put.called)

    def _create_slave_allocator(self, **kwargs):
        """
        Create a slave allocator for testing.
        :param kwargs: Any constructor parameters for the slave; if none are specified, test defaults will be used.
        :rtype: SlaveAllocator
        """
        return SlaveAllocator(Mock(spec_set=BuildSchedulerPool))

class AbortLoopForTesting(Exception):
    """
    An error we can raise to stop the while True loop in slave allocation
    """
