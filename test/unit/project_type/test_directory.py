from genty import genty, genty_dataset

from app.project_type.directory import Directory
from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.conf.configuration import Configuration


@genty
class TestDirectory(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        Configuration['timings_directory'] = '/var/besttimingsever'
        self.patch_abspath('app.project_type.directory.os.path.abspath', cwd='/usr/my_fake_cwd/')

    @genty_dataset(
        relative_project_dir=(
            'my_code/a_smart_project/',
            'UnitTests',
            '/var/besttimingsever/usr/my_fake_cwd/my_code/a_smart_project/UnitTests.timing.json'),
        absolute_project_dir=(
            '/Users/me/neato project',
            'Functional Tests',
            '/var/besttimingsever/Users/me/neato project/Functional Tests.timing.json'),
    )
    def test_timing_file_path(self, project_directory, fake_job_name, expected_timing_file_path):

        directory_env = Directory(project_directory)
        actual_timing_file_path = directory_env.timing_file_path(fake_job_name)

        self.assertEqual(actual_timing_file_path, expected_timing_file_path)
