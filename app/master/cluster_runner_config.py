import sys
import yaml

from app.master.atomizer import Atomizer
from app.master.job_config import JobConfig
from app.util import log


# clusterrunner.yaml config section names
SETUP_BUILD = 'setup_build'
TEARDOWN_BUILD = 'teardown_build'
COMMANDS = 'commands'
ATOMIZERS = 'atomizers'
MAX_EXECUTORS = 'max_executors'
MAX_EXECUTORS_PER_SLAVE = 'max_executors_per_slave'


class ClusterRunnerConfig(object):
    DEFAULT_MAX_EXECUTORS = sys.maxsize

    def __init__(self, raw_yaml_contents):
        """
        :param raw_yaml_contents: Raw string contents of project clusterrunner.yaml file
        :type raw_yaml_contents: string
        """
        self._job_configs = None
        self._logger = log.get_logger(__name__)
        self._raw_yaml_contents = raw_yaml_contents

    def get_job_config(self, job_name=None):
        """
        Get a list of job configs contained in this cluster runner config, optionally filtered by job names.
        :param job_name:
        :type job_name: str | None
        :return: The specified job config
        :rtype: JobConfig
        """
        if self._job_configs is None:
            self._parse_raw_config()

        if job_name is not None:
            if job_name not in self._job_configs:
                raise JobNotFoundError('The job "{}" was not found in the loaded config. '
                                       'Valid jobs are: {}'.format(job_name, self.get_job_names()))
            return self._job_configs[job_name]

        if len(self._job_configs) == 1:
            return list(self._job_configs.values())[0]

        raise JobNotSpecifiedError('Multiple jobs are defined in this project but you did not specify one. '
                                   'Specify one of the following job names: {}'.format(self.get_job_names()))

    def get_job_names(self):
        """
        Get the names of all the jobs defined in the associated config file.
        :return: A list of all job names in the config file
        :rtype: list[str]
        """
        if self._job_configs is None:
            self._parse_raw_config()

        return list(self._job_configs.keys())

    def _parse_raw_config(self):
        config = yaml.safe_load(self._raw_yaml_contents)
        self._validate(config)
        self._set_config(config)

    def _validate(self, config):
        """
        Validate the parsed yaml structure. This method raises on validation errors.
        :param config: The parsed yaml data
        :type config: dict
        """
        if not isinstance(config, dict):
            raise ConfigParseError('The yaml config file could not be parsed to a dictionary')

        required_fields = {COMMANDS, ATOMIZERS}
        allowed_fields_expected_types = {
            SETUP_BUILD: [(list, str)],  # (list, str) means this field should be a list of strings
            TEARDOWN_BUILD: [(list, str)],
            COMMANDS: [(list, str)],
            ATOMIZERS: [(list, dict)],  # (list, dict) means this field should be a list of dicts
            MAX_EXECUTORS: [int],
            MAX_EXECUTORS_PER_SLAVE: [int],
        }

        for job_name, job_config_sections in config.items():
            if not isinstance(job_config_sections, dict):
                raise ConfigValidationError('Invalid definition in project yaml file for job "{}".'.format(job_name))

            missing_required_fields = required_fields - job_config_sections.keys()
            if missing_required_fields:
                raise ConfigValidationError('Definition for job "{}" in project yaml is missing required config '
                                            'sections: {}.'.format(job_name, missing_required_fields))

            for config_section_name, config_section_value in job_config_sections.items():
                if config_section_name not in allowed_fields_expected_types:
                    raise ConfigValidationError('Definition for job "{}" in project yaml contains an invalid config '
                                                'section "{}".'.format(job_name, config_section_name))

                expected_section_types = allowed_fields_expected_types[config_section_name]
                actual_section_type = type(config_section_value)
                if actual_section_type is list:
                    # also check the type of the list items (assuming all list items have the same type as the first)
                    actual_section_type = (list, type(config_section_value[0]))

                if actual_section_type not in expected_section_types:
                    raise ConfigValidationError(
                        'Definition for job "{}" in project yaml contains an invalid value for config section "{}". '
                        'Parser expected one of {} but found {}.'
                        .format(job_name, config_section_name, expected_section_types, actual_section_type))

    def _set_config(self, config):
        """
        Translate the parsed and validated config data into JobConfig objects, and save the results to an attribute
        on this instance.
        :param config: Config values for one or more jobs, with job names as the keys
        :type config: dict [str, dict]
        """
        self._job_configs = {job_name: self._construct_job_config(job_name, job_values)
                             for job_name, job_values in config.items()}

        if len(self._job_configs) == 0:
            raise ConfigParseError('No jobs found in the config.')

    def _construct_job_config(self, job_name, job_values):
        """
        Produce a JobConfig object given a dictionary of values parsed from a yaml config file.
        :param job_name: The name of the job
        :type job_name: str
        :param job_values: The dict of config sections for this job as parsed from the yaml file
        :type job_values: dict
        :return: A JobConfig object wrapping the normalized data for the specified job
        :rtype: JobConfig
        """
        # Each value should be transformed from a list of commands to a single command string.
        setup_build = self._shell_command_list_to_single_command(job_values.get(SETUP_BUILD))
        teardown_build = self._shell_command_list_to_single_command(job_values.get(TEARDOWN_BUILD))
        command = self._shell_command_list_to_single_command(job_values[COMMANDS])

        atomizer = Atomizer(job_values[ATOMIZERS])
        max_executors = job_values.get(MAX_EXECUTORS, self.DEFAULT_MAX_EXECUTORS)
        max_executors_per_slave = job_values.get(MAX_EXECUTORS_PER_SLAVE, self.DEFAULT_MAX_EXECUTORS)

        return JobConfig(job_name, setup_build, teardown_build, command, atomizer, max_executors,
                         max_executors_per_slave)

    def _shell_command_list_to_single_command(self, commands):
        """
        Combines a list of commands into a single bash string
        :param commands: a list of commands, optionally ending with semicolons
        :type commands: list[str|None]
        :return: returns the concatenated shell command on success, or None if there was an error
        :rtype: string|None
        """
        if not isinstance(commands, list):
            return None

        # We should join the commands with double ampersands UNLESS the command already ends with a single ampersand.
        # A semicolon (or a double ampersand) is invalid syntax after a single ampersand.
        sanitized_commands = []
        for command in commands:
            if command is None:
                # skip `None` command in the commands list
                continue
            stripped_command = command.strip().rstrip(';')
            # If the command ends with an ampersand (single or double) we can leave the command alone (empty postfix)
            postfix = ' ' if stripped_command.strip().endswith('&') else ' && '
            sanitized_commands.append(stripped_command + postfix)

        # '&&' must not be appended to the command for the last shell command. For the sake of homogeneity of the
        # loop above, we just strip out the '&&' here.
        joined_commands = ''.join(sanitized_commands).strip()

        if joined_commands.endswith('&&'):
            joined_commands = joined_commands.rstrip('&')

        return joined_commands


class ConfigParseError(Exception):
    """
    The cluster runner config could not be parsed
    """


class JobNotFoundError(Exception):
    """
    The requested job could not be found in the config
    """


class JobNotSpecifiedError(Exception):
    """
    Multiple jobs were found in the config but none were specified
    """


class ConfigValidationError(Exception):
    """
    The cluster runner config was invalid
    """
