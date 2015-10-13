from genty import genty, genty_dataset

from app.master.job_config import JobConfig, ConfigValidationError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestJobConfig(BaseUnitTestCase):

    @genty_dataset(
        {'atomizers': [{'TESTPATH': 'atomizer command'}]},
        {'commands': ['shell command 1', 'shell command 2;']}
    )
    def test_construct_from_dict_raise_error_without_requried_fields(self, config_dict):
        with self.assertRaises(ConfigValidationError):
            JobConfig.construct_from_dict('some_job_name', config_dict)

    def test_construct_from_dict_for_valid_conf_with_only_required_fields(self):
        config_dict = {
            'commands': ['shell command 1', 'shell command 2;'],
            'atomizers': [{'TESTPATH': 'atomizer command'}],
        }
        job_config = JobConfig.construct_from_dict('some_job_name', config_dict)

        self.assertEquals(job_config.command, 'shell command 1 && shell command 2')
        self.assertEquals(job_config.name, 'some_job_name')

    def test_construct_from_dict_for_valid_conf_with_all_fields(self):
        config_dict = {
            'commands': ['shell command 1', 'shell command 2;'],
            'atomizers': [{'TESTPATH': 'atomizer command'}],
            'setup_build': ['setup command 1;', 'setup command 2;'],
            'teardown_build': ['teardown command 1;', 'teardown command 2;'],
            'max_executors': 100,
            'max_executors_per_slave': 2,
        }
        job_config = JobConfig.construct_from_dict('some_job_name', config_dict)

        self.assertEquals(job_config.command, 'shell command 1 && shell command 2')
        self.assertEquals(job_config.name, 'some_job_name')
        self.assertEquals(job_config.setup_build, 'setup command 1 && setup command 2')
        self.assertEquals(job_config.teardown_build, 'teardown command 1 && teardown command 2')
        self.assertEquals(job_config.max_executors, 100)
        self.assertEquals(job_config.max_executors_per_slave, 2)
