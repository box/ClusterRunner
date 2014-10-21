import yaml

from app.master.job_config import JobConfig
import app.util.fs
from app.util import log


class ClusterRunnerConfig(object):
    def __init__(self, raw_yaml_contents=None):
        self._job_configs = {}
        self._logger = log.get_logger(__name__)
        self._raw_yaml_contents = raw_yaml_contents

    def read(self, raw_yaml_contents=None):
        """
        :param raw_yaml_contents: raw string of boxci yaml file
        :type raw_yaml_contents: string | None
        """
        raw_yaml_contents = raw_yaml_contents or self._raw_yaml_contents
        config = yaml.safe_load(raw_yaml_contents)

        self._validate(config)
        self.set_config(config)

    def write(self, filename):
        """
        :param filename: file to write yaml to
        :type filename: string
        """
        serialized = yaml.dump(self._job_configs)
        app.util.fs.write_file(serialized, filename)

    def _validate(self, config):
        if not isinstance(config, dict):
            raise ConfigParseError('The yaml config file could not be parsed to a dictionary')
        required_fields = ['commands', 'atomizers']
        allowed_fields = ['setup_build', 'teardown_build', 'commands', 'atomizers', 'max_executors']
        for job_name, job_values in config.items():
            if job_values is None:
                raise ConfigValidationError('No definition found for job {}'.format(job_name))
            for field in required_fields:
                if not isinstance(job_values.get(field), list):
                    raise ConfigValidationError('For job "{}", expected the project yaml file to contain a list value '
                                                'for the "{}" key. Found "{}" instead'.format(field, job_name,
                                                                                              job_values.get(field)))
            for value_name in job_values.keys():
                if value_name not in allowed_fields:
                    raise ConfigValidationError(
                        'An invalid key "{}" was found in the config for job {}'.format(value_name, job_name))

    def set_config(self, config):
        """
        :param config: Config values for one or more jobs, with job names as the keys
        :type config: dict [str, dict]
        """
        self._job_configs = {
            job_name: self._construct_job_config(job_name, job_values) for job_name, job_values in config.items()
        }

        if len(self._job_configs) == 0:
            raise ConfigParseError('No jobs found in the config.')

    def job_names(self):
        return list(self._job_configs.keys())

    def get_job_config(self, job_name=None):
        """
        Get a list of job configs contained in this cluster runner config, optionally filtered by job names.
        :type job_name: str | None
        :rtype: JobConfig | None
        """
        if len(self._job_configs) == 0:
            self.read()

        if job_name is not None:
            if job_name not in self._job_configs:
                raise JobNotFoundError('The job {} was not found. Valid jobs are {}'.format(job_name, self.job_names()))
            return self._job_configs[job_name]

        if len(self._job_configs) == 1:
            return next(iter(self._job_configs.values()))

        raise JobNotSpecifiedError('Multiple jobs are defined in this project but you did not specify one. '
                                   'Specify one of the following job names: {}'.format(self.job_names()))

    def _construct_job_config(self, name, job_values):
        """
        Produces a JobConfig object given a dictionary of values parsed from a yaml config file
        :type name: str
        :type job_values: dict
        :return:
        """
        # Each value should be transformed from a list to a single command string
        setup_build = self._shell_command_list_to_single_command(job_values.get('setup_build'))
        teardown_build = self._shell_command_list_to_single_command(job_values.get('teardown_build'))
        command = self._shell_command_list_to_single_command(job_values.get('commands'))

        # Parse atomizers
        atomizers = job_values.get('atomizers')
        atomizer_commands = [self._atomizer_command(atomizer) for atomizer in atomizers]
        atomizer = self._shell_command_list_to_single_command(atomizer_commands)

        # Parse max_executors
        try:
            max_executors = int(job_values.get('max_executors'))
        except (ValueError, TypeError):
            self._logger.warning('The config value for max_processes is not parsable as an int.')
            max_executors = float('inf')

        return JobConfig(name, setup_build, teardown_build, command, atomizer, max_executors)

    def _atomizer_command(self, atomizer_element):
        """
        We support 3 types of atomizer commands, freeform shell strings, environment vars from shell strings,
        and environment vars from a path and a regex.
        :type atomizer_element: dict [str, str] | dict [str, dict] | str
        :rtype: str
        """
        if isinstance(atomizer_element, str):
            # Freeform atomizer shell command
            return atomizer_element
        if isinstance(atomizer_element, dict):
            # Environment var atomizer
            return self._atomizer_environment_variable(atomizer_element)
        raise ConfigParseError('Atomizer found but element is not a string or dictionary')

    def _atomizer_environment_variable(self, atomizer_element):
        """
        There are two types of environment var atomizers: shell command and regex.
        :type atomizer_element: dict [str, str] | dict [str, dict]
        :rtype: str
        """
        var_name = self._atomizer_environment_var_name(atomizer_element)
        first_element = next(iter(atomizer_element.values()))
        if isinstance(first_element, dict):
            # Regex environment var atomizer
            command = self._atomizer_regex(first_element)
        elif isinstance(first_element, str):
            # Shell command environment var atomizer
            command = first_element
        else:
            raise ConfigParseError('Atomizer for environment variable found but value is not a string or dictionary')

        return "{} | xargs -I {{}} echo 'export {}=\"'{{}}'\"'".format(command, var_name)

    def _atomizer_regex(self, regex_params):
        """
        A regex atomizer takes two params, the path and the regex.  We generate a command that returns all files
        in the path that match the regex.
        :type regex_params: dict [str, str]
        :rtype: str
        """
        if 'path' not in regex_params or 'regex' not in regex_params:
            raise ConfigParseError('Regex atomizer detected but it does not contain "path" and "regex" keys')
        # @todo: properly escape quotes in regex_params['regex'] and spaces in 'path'
        return 'find {} -regex "{}"'.format(regex_params['path'], regex_params['regex'])

    def _atomizer_environment_var_name(self, atomizer_element):
        """
        We use the dictionary key as the environment variable name
        :type atomizer_element: dict [str, str] | dict [str, dict]
        :return:
        """
        if len(atomizer_element) != 1:
            raise ConfigParseError(
                'Environment var atomizer should contain 1 key, actually contains {}'.format(len(atomizer_element)))

        return next(iter(atomizer_element.keys()))

    def _shell_command_list_to_single_command(self, commands):
        """
        Combines a list of commands into a single bash string
        :param commands: a list of commands, possibly ending with semicolons, but not guaranteed
        :type commands: list[str]
        :return: returns the concatenated shell command on success, or None if there was an error
        :rtype: string|None
        """
        if not isinstance(commands, list):
            return None

        # We should join the commands with double ampersands UNLESS the command already ends with a single ampersand.
        # A semicolon (or a double ampersand) is invalid syntax after a single ampersand.
        sanitized_commands = []
        for command in commands:
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
    pass


class JobNotFoundError(Exception):
    """
    The requested job could not be found in the config
    """
    pass


class JobNotSpecifiedError(Exception):
    """
    Multiple jobs were found in the config but none were specified
    """
    pass


class ConfigValidationError(Exception):
    """
    The cluster runner config was invalid
    """
    pass
