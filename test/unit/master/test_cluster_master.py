from unittest.mock import MagicMock

from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.master.slave import Slave
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestClusterMaster(BaseUnitTestCase):

    def setUp(self):
        self.patch('app.util.fs.create_dir')
        self.patch('shutil.rmtree')
        super().setUp()
        self.patch('app.master.build.app.util')  # stub out util functions since these often interact with the fs

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
