from collections import MutableMapping
from concurrent.futures import ThreadPoolExecutor
import os
from os.path import isfile
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sys import maxsize

from genty import genty, genty_dataset
from unittest.mock import MagicMock, Mock

from app.database.build_store import BuildStore
from test.framework.base_unit_test_case import BaseUnitTestCase
from app.master.atomizer import Atomizer
from app.master.build import Build, BuildStatus
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.master.job_config import JobConfig
from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration


TEST_DB_NAME = 'test.db'
TEST_DB_URL = 'sqlite:///test.db'


@genty
class TestBuildStore(BaseUnitTestCase):
    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')
        self.patch('os.makedirs')
        self.mock_slave_allocator = self.patch('app.master.cluster_master.SlaveAllocator').return_value
        self.mock_scheduler_pool = self.patch('app.master.cluster_master.BuildSchedulerPool').return_value

        # Two threads are ran everytime we start up the ClusterMaster. We redirect the calls to
        # `ThreadPoolExecutor.submit` through a mock proxy so we can capture events.
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=2)
        self._thread_pool_executor_cls = self.patch('app.master.cluster_master.ThreadPoolExecutor')
        self._thread_pool_executor_cls.return_value.submit.side_effect = \
            self.thread_pool_executor.submit

        self.patch('app.master.build.util.create_project_type').return_value = self._create_mock_project_type()
        Configuration['database_name'] = TEST_DB_NAME
        Configuration['database_url'] = TEST_DB_URL
        self._build_store = BuildStore()

    def tearDown(self):
        super().tearDown()
        self.thread_pool_executor.shutdown()

    def tearDownClass():
        # Delete testing database after we're done
        if isfile(TEST_DB_NAME):
            os.remove(TEST_DB_NAME)
        else:
            print('Warning: Unable to locate test database file on tearDownClass.')

    @genty_dataset(
        first_build=(1,),
        second_build=(2,),
        third_build=(3,),
    )
    def test_add_build_to_store_sets_build_id(self, expected_build_id):
        build = Build(BuildRequest({}))
        self._build_store.add(build)
        self.assertEqual(build.build_id(), expected_build_id, 'The wrong build_id was set.')

    @genty_dataset(
        build_id_1=(1, 1),
        build_id_invalid=(1000, None),
    )
    def test_get_build_from_store(self, build_id, expected_build_id):
        build = self._build_store.get(build_id)
        if build is None:
            self.assertEqual(None, expected_build_id, 'Couldn\'t find build in BuildStore.')
        else:
            self.assertEqual(build.build_id(), expected_build_id, 'Got the wrong build from BuildStore.')

    def test_deserialized_build_api_representation_is_same_as_original_build_no_failures(self):
        build = Build(BuildRequest({
            'type': 'git',
            'url': 'git@name/repo.git',
            'job_name': 'Example'
        }))
        build.generate_project_type()

        self._build_store.add(build)
        reconstructed_build = self._build_store._reconstruct_build(build.build_id())

        original_build_results = build.api_representation()
        reconstructed_build_results = reconstructed_build.api_representation()
        diff = self._compare_dictionaries_with_same_keys(original_build_results, reconstructed_build_results)

        # The build_project_directory is an auto generated tmp directory -- these will never be the same
        diff.pop('request_params|build_project_directory', None)

        self.assertEqual(diff, {}, 'Deserialized build is not the same as the original build.')

    def _create_job_config(self) -> JobConfig:
        max_executors = max_executors_per_slave = maxsize
        atomizer = Atomizer([{'FAKE': 'fake atomizer command'}])
        return JobConfig('', '', '', '', atomizer, max_executors, max_executors_per_slave)

    def _create_mock_project_type(self) -> MagicMock:
        return MagicMock(spec_set=ProjectType())

    def _compare_dictionaries_with_same_keys(self, d1: dict, d2: dict) -> dict:
        """
        Find all the keys in two nested dictionaries that differ in value. This also considers
        a key that is only unique to one dictionary to be a diff.
        :param d1: The first dictionary to diff.
        :param d1: The second dictionary to diff.
        """
        diffs = {}
        d1 = self._flatten(d1)
        d2 = self._flatten(d2)
        for name, value in d1.items():
            if not (name in d2 and d2[name] == value):
                diffs[name] = (value, d2.get(name, None))
        for name, value in d2.items():
            if not (name in d1 and d1[name] == value):
                diffs[name] = (value, d1.get(name, None))
        return diffs

    def _flatten(self, d, parent_key=''):
        """
        Flatten a nested dictionary. Join together parents with children using a pipe character.
        :param d: Dictionary to flatten.
        :param parent_key: Name of the previous key. These are concatenated together
                           to form the flattened key.
        """
        items = []
        for k, v in d.items():
            new_key = parent_key + '|' + k if parent_key else k
            if isinstance(v, MutableMapping):
                items.extend(self._flatten(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)
