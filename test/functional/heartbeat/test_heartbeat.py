from requests.exceptions import ConnectionError
from unittest import skipIf

from app.util.process_utils import is_windows
from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase

@skipIf(is_windows(), 'Fails on AppVeyor; see issue #345')
class TestHeartbeat(BaseFunctionalTestCase):
	def test_worker_failure_should_mark_worker_offline(self):
		manager = self.cluster.start_manager(unresponsive_workers_cleanup_interval=5)
		workers = self.cluster.start_worker(num_executors_per_worker=1, start_port=43001, heartbeat_interval=5,
										  heartbeat_failure_threshold=1)

		# verify that the worker is connected
		self.assertEqual(True, manager.get_worker_status(1).get('is_alive'))

		# kill the worker in non graceful manner and verify that manager still thinks it is connected
		self.cluster.kill_workers(kill_gracefully=False)
		self.cluster.block_until_n_workers_dead(1,5)
		self.assertEqual(True, manager.get_worker_status(1).get('is_alive'))

		# wait for the next heartbeat run which marks the worker offline
		self.cluster.block_until_n_workers_marked_dead_in_manager(1,10)
		self.assertEqual(False, manager.get_worker_status(1).get('is_alive'))

	def test_manager_failure_should_kill_the_worker_process(self):
		manager = self.cluster.start_manager(unresponsive_workers_cleanup_interval=5)
		worker = self.cluster.start_worker(num_executors_per_worker=1, start_port=43001, heartbeat_interval=5,
										  heartbeat_failure_threshold=1)
		# verify that the worker is connected
		self.assertEqual(True,worker.get_worker_status()['worker']['is_alive'])

		# kill the manager and verify that the worker dies after heartbeat failure
		self.cluster.kill_manager()
		self.cluster.block_until_n_workers_dead(1,40)
		self.assertRaises(ConnectionError, worker.get_worker_status)

