from unittest.mock import MagicMock, Mock
from box.test.genty import genty, genty_dataset

from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.master.slave import Slave
from app.util.exceptions import ItemNotFoundError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterMaster(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('shutil.rmtree')

    def test_add_idle_slave_marks_build_finished_when_slaves_are_done(self):
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
        master.add_idle_slave(slave1)
        build1.finish.assert_called_once_with()

    def test_add_idle_slave_does_not_mark_build_finished_when_slaves_not_done(self):
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
        master.add_idle_slave(slave1)
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

    def test_update_build_with_valid_params_succeeds(self):
        build_id = 1
        update_params = {'key': 'value'}
        master = ClusterMaster()
        build = Mock()
        master._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        success, response = master.handle_request_to_update_build(build_id, update_params)

        build.update_state.assert_called_once_with(update_params)
        self.assertTrue(success)
        self.assertEqual(response, {})
