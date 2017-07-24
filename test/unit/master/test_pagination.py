from typing import Optional
from threading import Event

from genty import genty, genty_dataset
from hypothesis import given
from hypothesis.strategies import text, dictionaries, integers
from unittest.mock import MagicMock, Mock

from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.slave.cluster_slave import SlaveState
from app.util.exceptions import BadRequestError, ItemNotFoundError
from app.web_framework.cluster_base_handler import ClusterBaseHandler, pagination_constants
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterMaster(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')
        self.patch('os.makedirs')
        self.mock_slave_allocator = self.patch('app.master.cluster_master.SlaveAllocator').return_value
        self.mock_scheduler_pool = self.patch('app.master.cluster_master.BuildSchedulerPool').return_value

    @genty_dataset(
        no_params=(
            None, None,
            pagination_constants['DEFAULT_OFFSET'] + 1,
            pagination_constants['DEFAULT_OFFSET'] + pagination_constants['DEFAULT_LIMIT']
        ),
        offset_param=(
            50, None,
            50 + 1,
            50 + pagination_constants['DEFAULT_LIMIT']
        ),
        limit_param=(
            None, 100,
            pagination_constants['DEFAULT_OFFSET'] + 1,
            pagination_constants['DEFAULT_OFFSET'] + 100
        ),
        offset_and_limit_params=(
            53, 100,
            53 + 1,
            53 + 100
        ),
        low_offset=(
            None, 2,
            pagination_constants['DEFAULT_OFFSET'] + 1,
            pagination_constants['DEFAULT_OFFSET'] + 2
        ),
        too_high_offset=(
            1000, 100,
            pagination_constants['DEFAULT_OFFSET'] + 1,
            pagination_constants['DEFAULT_OFFSET'] + 100
        ),
        too_high_limit=(
            None, 1000,
            pagination_constants['DEFAULT_OFFSET'] + 1,
            pagination_constants['DEFAULT_OFFSET'] + pagination_constants['MAX_LIMIT']
        ),
        negative_offset=(
            -50, None,
            0 + 1,
            pagination_constants['DEFAULT_OFFSET'] + pagination_constants['DEFAULT_LIMIT']
        ),
        negative_limit=(
            None, -50,
            None,
            None
        ),
    )
    def test_pagination_request_with_query_params(
            self,
            offset: Optional[int],
            limit: Optional[int],
            expected_first_build_id: int,
            expected_last_build_id: int,
            ):
        master = ClusterMaster()
        for build_id in range(1, 501):
            build_mock = Mock(spec=Build)
            build_mock.build_id = build_id
            master._all_builds_by_id[build_id] = build_mock

        offset, limit = ClusterBaseHandler._validate_arguments(offset, limit)
        requested_builds = master.builds(offset, limit)
        
        id_of_first_build = requested_builds[0].build_id if len(requested_builds) else None
        id_of_last_build = requested_builds[-1].build_id if len(requested_builds) else None
        num_builds = len(requested_builds)

        self.assertEqual(id_of_first_build, expected_first_build_id, 'Received the wrong first build from request')
        self.assertEqual(id_of_last_build, expected_last_build_id, 'Received the wrong last build from request')
        self.assertLessEqual(num_builds, pagination_constants['MAX_LIMIT'], 'Received too many builds from request')


    @genty_dataset(
        no_params=(None, None, pagination_constants['DEFAULT_OFFSET'], pagination_constants['DEFAULT_LIMIT']),
        offset_param=(50, None, 50, pagination_constants['DEFAULT_LIMIT']),
        limit_param=(None, 50, pagination_constants['DEFAULT_OFFSET'], 50),
        offset_and_limit_param=(50, 100, 50, 100),
        negative_offset_param=(-50, None, 0, pagination_constants['DEFAULT_LIMIT']),
        negative_limit_param=(None, -50, pagination_constants['DEFAULT_OFFSET'], 0),
    )
    def test_pagination_query_params(
            self,
            offset: Optional[int],
            limit: Optional[int],
            expected_offset: int,
            expected_limit: int,
            ):
        actual_offset, actual_limit = ClusterBaseHandler._validate_arguments(offset, limit)
        self.assertEqual(actual_offset, expected_offset, 'Actual offset does not match expected offset')
        self.assertEqual(actual_limit, expected_limit, 'Actual limit does not match expected limit')
