from box.test.genty import genty, genty_dataset

from app.master.cluster_runner_config import ClusterRunnerConfig, ConfigParseError, ConfigValidationError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterRunnerConfig(BaseUnitTestCase):

    _COMPLETE_VALID_CONFIG = """
    Best Job Ever:
        max_executors: 21
        setup_build:
            - echo "This is setup! Woo!"  # no semicolons in this section
            - sleep 1
        commands:
            - echo "Now I'm doing $THE_THING!";  # semicolons in this section
            - echo "Semicolons are fun." > /tmp/all_my_hard_work.txt;
        atomizers:
            - THE_THING: printf 'something with a number %d\\n' {1..50}
    """

    _MULTI_JOB_CONFIG = """
    First Job:
        commands:
            - echo "go"
        atomizers:
            - ENV_VAR: echo "atom"
    Second Job:
        commands:
            - echo "go"
        atomizers:
            - ENV_VAR: echo "atom"
    """

    _FREEFORM_ATOMIZER = """
    PHPUnit:
        commands:
            - echo "go"
        atomizers:
            - "export VARNAME='asdf'"
    """

    _REGEX_ATOMIZER = """
    PHPUnit:
        commands:
            - echo "go"
        atomizers:
            - VAR_NAME:
                path: /path/to/project
                regex: "[s|S]imple regex"
    """

    _MINIMAL_CONFIG = """
    PHPUnit:
        commands:
            - echo "go"
        atomizers:
            - ENV_VAR: find . -name "*.php"
    """

    _EMPTY_CONFIG = """
    PHPUnit:
    """

    _NO_COMMAND_INVALID_CONFIG = """
    PHPUnit:
        max_executors: 5
        setup_build:
            - echo "I don't know what I'm doing."
        atomizers:
            - VARNAME: sleep 123
    """

    _BACKGROUND_TASK_CONFIG = """
    PHPUnit:
        max_executors: 5
        setup_build:
            - echo "in the background" &
            - echo "in the foreground" ;
            - echo "another thing"
        atomizers:
            - VARNAME: sleep1
        commands:
            - echo "go"
    """

    @genty_dataset(
        ('name', 'Best Job Ever'),
        ('max_executors', 21),
        ('setup_build', 'echo "This is setup! Woo!" && sleep 1 '),
        ('command', 'echo "Now I\'m doing $THE_THING!" && echo "Semicolons are fun." > /tmp/all_my_hard_work.txt '),
        ('atomizer',
         'printf \'something with a number %d\\n\' {1..50} | xargs -I {} echo \'export THE_THING="\'{}\'"\' '),
    )
    def test_all_conf_properties_are_correctly_parsed(self, conf_method_name, expected_value):
        config = ClusterRunnerConfig(self._COMPLETE_VALID_CONFIG)
        job_config = config.get_job_config()
        actual_value = getattr(job_config, conf_method_name)
        self.assertEqual(actual_value, expected_value,
                         'The output of {}() should match the expected value.'.format(conf_method_name))

    @genty_dataset(
        ('max_executors', float('inf')),
        ('setup_build', None),
    )
    def test_undefined_conf_properties_return_default_values(self, conf_method_name, expected_value):
        config = ClusterRunnerConfig(self._MINIMAL_CONFIG)
        job_config = config.get_job_config()
        actual_value = getattr(job_config, conf_method_name)

        self.assertEqual(actual_value, expected_value,
                         'The default output of {}() should match the expected value.'.format(conf_method_name))

    @genty_dataset(
        valid_config=(_COMPLETE_VALID_CONFIG, True),
        empty_config=(_EMPTY_CONFIG, False),
        invalid_config=(_NO_COMMAND_INVALID_CONFIG, False),
    )
    def test_valid_configs_are_detected(self, config_contents, is_expected_valid):
        config = ClusterRunnerConfig(config_contents)
        try:
            config.get_job_config()
        except (ConfigParseError, ConfigValidationError) as e:
            self.assertFalse(is_expected_valid, 'Config is valid, but threw {}'.format(type(e)))
            return
        self.assertTrue(is_expected_valid, 'Config is not valid, but parsed without error')

    @genty_dataset(
        _FREEFORM_ATOMIZER,
        _REGEX_ATOMIZER
    )
    def test_atomizer_types(self, config_contents):
        config = ClusterRunnerConfig(config_contents)
        config.get_job_config()

    def test_get_specific_job_config(self):
        config = ClusterRunnerConfig(self._MULTI_JOB_CONFIG)
        job_config = config.get_job_config('Second Job')
        self.assertEqual('Second Job', job_config.name, '')
        job_config = config.get_job_config('First Job')
        self.assertEqual('First Job', job_config.name, '')

    def test_config_with_background_task(self):
        config = ClusterRunnerConfig(self._BACKGROUND_TASK_CONFIG)
        job_config = config.get_job_config()
        self.assertEqual(job_config.setup_build,
                         'echo "in the background" & echo "in the foreground"  && echo "another thing" ')
