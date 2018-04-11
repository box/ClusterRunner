from requests.exceptions import ConnectionError
from unittest import skipIf

from app.util.process_utils import is_windows
from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase

@skipIf(is_windows(), 'Fails on AppVeyor; see issue #345')
class TestHeartbeat(BaseFunctionalTestCase):
	def test_slave_failure_should_mark_slave_offline(self):
		master = self.cluster.start_master(unresponsive_slaves_cleanup_interval=5)
		slaves = self.cluster.start_slave(num_executors_per_slave=1, start_port=43001, heartbeat_interval=5,
										  heartbeat_failure_threshold=1)

		# verify that the slave is connected
		self.assertEqual(True, master.get_slave_status(1).get('is_alive'))

		# kill the slave in non graceful manner and verify that master still thinks it is connected
		self.cluster.kill_slaves(kill_gracefully=False)
		self.cluster.block_until_n_slaves_dead(1,5)
		self.assertEqual(True, master.get_slave_status(1).get('is_alive'))

		# wait for the next heartbeat run which marks the slave offline
		self.cluster.block_until_n_slaves_marked_dead_in_master(1,10)
		self.assertEqual(False, master.get_slave_status(1).get('is_alive'))

	def test_master_failure_should_kill_the_slave_process(self):
		master = self.cluster.start_master(unresponsive_slaves_cleanup_interval=5)
		slave = self.cluster.start_slave(num_executors_per_slave=1, start_port=43001, heartbeat_interval=5,
										  heartbeat_failure_threshold=1)
		# verify that the slave is connected
		self.assertEqual(True,slave.get_slave_status()['slave']['is_alive'])

		# kill the master and verify that the slave dies after heartbeat failure
		self.cluster.kill_master()
		self.cluster.block_until_n_slaves_dead(1,40)
		self.assertRaises(ConnectionError, slave.get_slave_status)

