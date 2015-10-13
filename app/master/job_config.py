import sys

from app.master.atomizer import Atomizer


# config section names/keys
SETUP_BUILD = 'setup_build'
TEARDOWN_BUILD = 'teardown_build'
COMMANDS = 'commands'
ATOMIZERS = 'atomizers'
MAX_EXECUTORS = 'max_executors'
MAX_EXECUTORS_PER_SLAVE = 'max_executors_per_slave'


class JobConfig(object):
    """
    This class represents a single ClusterRunner job definition.
    """
    DEFAULT_MAX_EXECUTORS = sys.maxsize

    def __init__(self, name, setup_build, teardown_build, command, atomizer, max_executors, max_executors_per_slave):
        """
        :type name: str
        :type setup_build: list[str] | None
        :type teardown_build: list[str] | None
        :type command: list[str]
        :type atomizer: Atomizer
        :type max_executors: int | None
        :type max_executors_per_slave: int | None
        """
        self.name = name
        self.setup_build = setup_build
        self.teardown_build = teardown_build
        self.command = command
        self.atomizer = atomizer
        self.max_executors = max_executors
        self.max_executors_per_slave = max_executors_per_slave

    @classmethod
    def construct_from_dict(cls, name, config_dict):
        """
        First validate the config_dict contents. Raises an exception if validation fails.
        Upon validation success, return an instance of JobConfig.

        :param name: The name of this job configuration.
        :type name: str
        :param config_dict: a dictionary with the keys being config sections (e.g.: setup_build, commands, etc)
        :type config_dict: dict
        :return: JobConfig
        """
        cls._validate(name, config_dict)
        return cls._unpack(name, config_dict)

    @classmethod
    def _validate(cls, name, config_dict):
        """
        Raises a ConfigValidationError in case of an invalid configuration.

        :type name: str
        :type config_dict: dict
        :rtype: None
        """
        required_fields = {COMMANDS, ATOMIZERS}
        allowed_fields_expected_types = {
            SETUP_BUILD: [(list, str)],  # (list, str) means this field should be a list of strings
            TEARDOWN_BUILD: [(list, str)],
            COMMANDS: [(list, str)],
            ATOMIZERS: [(list, dict)],  # (list, dict) means this field should be a list of dicts
            MAX_EXECUTORS: [int],
            MAX_EXECUTORS_PER_SLAVE: [int],
        }

        if not isinstance(config_dict, dict):
            raise ConfigValidationError('Passed in configuration is not a dictionary for job: "{}".'.format(name))

        missing_required_fields = required_fields - config_dict.keys()
        if missing_required_fields:
            raise ConfigValidationError('Definition for job "{}" is missing required config sections: {}'
                                        .format(name, missing_required_fields))

        for config_section_name, config_section_value in config_dict.items():
            if config_section_name not in allowed_fields_expected_types:
                raise ConfigValidationError('Definition for job "{}" contains an invalid config section "{}".'
                                            .format(name, config_section_name))

            expected_section_types = allowed_fields_expected_types[config_section_name]
            actual_section_type = type(config_section_value)
            if actual_section_type is list:
                # also check the type of the list items (assuming all list items have the same type as the first)
                actual_section_type = (list, type(config_section_value[0]))

            if actual_section_type not in expected_section_types:
                raise ConfigValidationError(
                    'Definition for job "{}" contains an invalid value for config section "{}". '
                    'Parser expected one of {} but found {}.'
                    .format(name, config_section_name, expected_section_types, actual_section_type))

    @classmethod
    def _unpack(cls, name, config_dict):
        """
        Set class attributes from config dictionary.

        :type name: str
        :type config_dict: dict
        :rtype: JobConfig
        """
        setup_build = cls._shell_command_list_to_single_command(config_dict.get(SETUP_BUILD))
        teardown_build = cls._shell_command_list_to_single_command(config_dict.get(TEARDOWN_BUILD))
        command = cls._shell_command_list_to_single_command(config_dict[COMMANDS])
        atomizer = Atomizer(config_dict[ATOMIZERS])
        max_executors = config_dict.get(MAX_EXECUTORS, cls.DEFAULT_MAX_EXECUTORS)
        max_executors_per_slave = config_dict.get(MAX_EXECUTORS_PER_SLAVE, cls.DEFAULT_MAX_EXECUTORS)
        return cls(name, setup_build, teardown_build, command, atomizer, max_executors, max_executors_per_slave)

    @classmethod
    def _shell_command_list_to_single_command(cls, commands):
        """
        Combines a list of commands into a single command string

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
            joined_commands = joined_commands.rstrip('&').strip()

        return joined_commands


class ConfigValidationError(Exception):
    """
    The cluster runner config was invalid
    """
