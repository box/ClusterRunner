import os
from os.path import join, splitdrive

from genty import genty, genty_dataset

from app.project_type.directory import Directory
from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.conf.configuration import Configuration


@genty
class TestDirectory(BaseUnitTestCase):

    # os.getcwd() but without mount point or leading os.sep
    # e.g. '/var/bar' would become 'var/bar' on POSIX and 'c:\\temp\\foo' would become 'temp\\foo'
    _CWD_SYS_PATH_WITHOUT_SEP = splitdrive(os.getcwd())[1][len(os.sep):]
    _TIMINGS_DIR_SYS_PATH = join(os.getcwd(), 'var', 'besttimingserver')

    def setUp(self):
        super().setUp()
        Configuration['timings_directory'] = self._TIMINGS_DIR_SYS_PATH

    # Using `os.path.join` here instead of hard coding the path so the test is cross-platform.
    @genty_dataset(
        relative_project_dir=(
            join('my_code', 'a_smart_project'),
            'UnitTests',
            join(
                _TIMINGS_DIR_SYS_PATH,
                _CWD_SYS_PATH_WITHOUT_SEP,
                'my_code',
                'a_smart_project',
                'UnitTests.timing.json',
            ),
        ),
        absolute_project_dir=(
            join(os.getcwd(), 'Users', 'me', 'neato project'),
            'Functional Tests',
            join(
                _TIMINGS_DIR_SYS_PATH,
                _CWD_SYS_PATH_WITHOUT_SEP,
                'Users',
                'me',
                'neato project',
                'Functional Tests.timing.json',
            ),
        ),
    )
    def test_timing_file_path(self, project_directory, fake_job_name, expected_timing_file_path):
        directory_env = Directory(project_directory)
        actual_timing_file_path = directory_env.timing_file_path(fake_job_name)

        self.assertEqual(actual_timing_file_path, expected_timing_file_path)

    @genty_dataset(
        (True, False),
        (False, True),
    )
    def test_fetch_project_raises_runtime_error_only_if_project_dir_does_not_exist(
            self, expect_dir_exists,
            expect_runtime_error,
    ):
        # Arrange
        directory_env = Directory(join(os.getcwd(), 'my_project'))
        mock_os_path_isdir = self.patch('os.path.isdir')
        mock_os_path_isdir.return_value = expect_dir_exists
        self.patch('app.project_type.directory.node')

        # Act & Assert
        if expect_runtime_error:
            with self.assertRaises(RuntimeError):
                directory_env._fetch_project()
        else:
            directory_env._fetch_project()
