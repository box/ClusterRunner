from hypothesis import given
from hypothesis.strategies import text, dictionaries, integers
from test.framework.base_unit_test_case import BaseUnitTestCase

from app.master.build import Build
from app.master.cluster_master import ClusterMaster


class TestClusterMaster(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')
        self.patch('os.makedirs')

    @given(dictionaries(text(), text()))
    def test_handle_request_for_new_build(self, build_params):
        master = ClusterMaster()
        master.handle_request_for_new_build(build_params)

    @given(integers(), dictionaries(text(), text()))
    def test_handle_request_to_update_build(self, build_id, update_params):
        master = ClusterMaster()
        master._all_builds_by_id = {build_id: Build({})}
        master.handle_request_to_update_build(build_id, update_params)
