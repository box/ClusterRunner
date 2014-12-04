from unittest.mock import MagicMock
from box.test.genty import genty, genty_dataset

from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.master.slave import Slave
from app.slave.cluster_slave import SlaveState
from app.util.exceptions import BadRequestError, ItemNotFoundError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterMaster(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('shutil.rmtree')

    def test_updating_slave_to_idle_state_marks_build_finished_when_slaves_are_done(self):
        master = ClusterMaster()
        slave1 = Slave('', 1)
        slave2 = Slave('', 1)
        slave3 = Slave('', 1)
        slave1.current_build_id = 1
        slave2.current_build_id = None
        slave3.current_build_id = 3
        build1 = Build(BuildRequest({}))
        master._all_slaves_by_url = {'1': slave1, '2': slave2, '3': slave3}
        master._all_builds_by_id = {1: build1}
        build1._build_id = 1
        build1.finish = MagicMock()
        master.handle_slave_state_update(slave1, SlaveState.IDLE)
        build1.finish.assert_called_once_with()

    def test_updating_slave_to_idle_state_does_not_mark_build_finished_when_slaves_not_done(self):
        master = ClusterMaster()
        slave1 = Slave('', 1)
        slave2 = Slave('', 1)
        slave3 = Slave('', 1)
        slave1.current_build_id = 1
        slave2.current_build_id = None
        slave3.current_build_id = 1
        build1 = Build(BuildRequest({}))
        master._all_slaves_by_url = {'1': slave1, '2': slave2, '3': slave3}
        master._all_builds_by_id = {1: build1}
        build1._build_id = 1
        build1.finish = MagicMock()
        master.handle_slave_state_update(slave1, SlaveState.IDLE)
        self.assertFalse(build1.finish.called)

    @genty_dataset(
        slave_id_specified=({'slave_id': 400},),
        slave_url_specified=({'slave_url': 'michelangelo.turtles.gov'},),
    )
    def test_get_slave_raises_exception_on_slave_not_found(self, get_slave_kwargs):
        master = ClusterMaster()
        master.connect_new_slave('raphael.turtles.gov', 10)
        master.connect_new_slave('leonardo.turtles.gov', 10)
        master.connect_new_slave('donatello.turtles.gov', 10)

        with self.assertRaises(ItemNotFoundError):
            master.get_slave(**get_slave_kwargs)

    @genty_dataset(
        both_arguments_specified=({'slave_id': 1, 'slave_url': 'raphael.turtles.gov'},),
        neither_argument_specified=({},),
    )
    def test_get_slave_raises_exception_on_invalid_arguments(self, get_slave_kwargs):
        master = ClusterMaster()
        master.connect_new_slave('raphael.turtles.gov', 10)

        with self.assertRaises(ValueError):
            master.get_slave(**get_slave_kwargs)

    def test_get_slave_returns_expected_value_given_valid_arguments(self):
        master = ClusterMaster()
        master.connect_new_slave('raphael.turtles.gov', 10)
        master.connect_new_slave('leonardo.turtles.gov', 10)
        master.connect_new_slave('donatello.turtles.gov', 10)

        actual_slave_by_id = master.get_slave(slave_id=2)
        actual_slave_by_url = master.get_slave(slave_url='leonardo.turtles.gov')

        self.assertEqual(2, actual_slave_by_id.id, 'Retrieved slave should have the same id as requested.')
        self.assertEqual('leonardo.turtles.gov', actual_slave_by_url.url,
                         'Retrieved slave should have the same url as requested.')

    def test_updating_slave_to_disconnected_state_should_mark_slave_as_dead(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_new_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)
        self.assertTrue(slave.is_alive)

        master.handle_slave_state_update(slave, SlaveState.DISCONNECTED)

        self.assertFalse(slave.is_alive)

    def test_updating_slave_to_setup_completed_state_should_tell_build_to_begin_subjob_execution(self):
        master = ClusterMaster()
        fake_build = MagicMock()
        master.get_build = MagicMock(return_value=fake_build)
        slave_url = 'raphael.turtles.gov'
        master.connect_new_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)

        master.handle_slave_state_update(slave, SlaveState.SETUP_COMPLETED)

        fake_build.begin_subjob_executions_on_slave.assert_called_once_with(slave)

    def test_updating_slave_to_nonexistent_state_should_raise_bad_request_error(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_new_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)

        with self.assertRaises(BadRequestError):
            master.handle_slave_state_update(slave, 'NONEXISTENT_STATE')
