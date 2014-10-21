from app.project_type.docker import Docker
from app.util.conf.configuration import Configuration
from app.util.conf.slave_config_loader import SlaveConfigLoader
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestDocker(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        SlaveConfigLoader().configure_defaults(Configuration.singleton())
        SlaveConfigLoader().configure_postload(Configuration.singleton())

    def test_timing_file_path_for_image_with_no_tag(self):
        docker_env = Docker('pod4101-automation1102.pod.box.net:5000/webapp_v5_dev', '/some_directory_doesnt_matter')
        timing_file = docker_env.timing_file_path('QUnit')
        self.assertEquals(
            Configuration['base_directory'] +
            '/timings/master/pod4101-automation1102.pod.box.net5000webapp_v5_dev/QUnit.timing.json',
            timing_file
        )

    def test_timing_file_path_for_image_with_tag(self):
        docker_env = Docker('pod4101-automation1102.pod.box.net:5000/webapp_v5_dev:latest', '/some_directory_doesnt_matter')
        timing_file = docker_env.timing_file_path('QUnit')
        self.assertEquals(
            Configuration['base_directory'] +
            '/timings/master/pod4101-automation1102.pod.box.net5000webapp_v5_dev/QUnit.timing.json',
            timing_file
        )
