from os.path import dirname, join, realpath, expanduser, isdir
from os import chmod
import platform
import sys
import shutil

from app.util import autoversioning, fs
from app.util.conf.config_file import ConfigFile


BASE_CONFIG_FILE_SECTION = 'general'


class BaseConfigLoader(object):

    CONFIG_FILE_SECTION = ''  # Override value in subclasses to load additional config.

    def configure_defaults(self, conf):
        """
        This is the base configuration. All default configuration values belong here. These values may be overridden by
        other configurations.
        :type conf: Configuration
        """
        if getattr(sys, 'frozen', False):
            root_directory = dirname(sys.executable)  # frozen
        else:
            root_directory = dirname(dirname(dirname(dirname(realpath(__file__)))))  # unfrozen

        conf.set('secret', None)  # This must be overridden by conf or the service will not start for security reasons

        conf.set('root_directory', root_directory)  # the root directory of the application
        conf.set('main_executable_path', sys.argv[0])
        conf.set('version', autoversioning.get_version())

        # If the user installed ClusterRunner manually, the directories used by the manual install should take
        # precedence over the default install location (the home directory).
        static_configured_base_directory = join('/var', 'lib', 'clusterrunner')

        if isdir(static_configured_base_directory):
            base_directory = static_configured_base_directory
        else:
            base_directory = join(expanduser('~/'), '.clusterrunner')

        # where all of the clusterrunner specific files will be stored (other than source code)
        conf.set('base_directory', base_directory)
        # the path to the clusterrunner config file. We have to specify this in defaults since it cannot depend on
        # values in the file it refers to.
        conf.set('config_file', join(base_directory, 'clusterrunner.conf'))

        # Where the clusterrunner service will save the process id to. These settings are set in base_config_loader
        # and not in master_config_loader and slave_config_loader because CLI tools such as "clusterrunner stop"
        # needs to read in these settings.
        conf.set('master_pid_file', join(base_directory, '.clusterrunner_master.pid'))
        conf.set('slave_pid_file', join(base_directory, '.clusterrunner_slave.pid'))

        # contains symlinks to build-specific repos
        conf.set('build_symlink_directory', join('/tmp', 'clusterrunner_build_symlinks'))
        # where the repos are cloned to
        conf.set('repo_directory', None)

        conf.set('project_yaml_filename', 'clusterrunner.yaml')

        conf.set('log_file', None)
        conf.set('log_level', 'DEBUG')
        conf.set('max_log_file_size', 1024 * 1024 * 50)  # 50mb
        conf.set('max_log_file_backups', 5)

        # set eventlog file conf values to None to disable eventlogs by default
        conf.set('log_filename', 'clusterrunner_default.log')
        conf.set('eventlog_filename', 'eventlog_default.log')
        conf.set('eventlog_file', None)
        conf.set('max_eventlog_file_size', 1024 * 1024 * 50)  # 50mb
        conf.set('max_eventlog_file_backups', 5)
        conf.set('hostname', platform.node())
        conf.set('master_hostname', 'localhost')
        conf.set('master_port', '43000')
        conf.set('slaves', ['localhost'])

        # Strict host key checking on git remote operations, disabled by default
        conf.set('git_strict_host_key_checking', False)

        # CORS support - a regex to match against allowed API request origins, or None to disable CORS
        conf.set('cors_allowed_origins_regex', None)

        # Helper executables
        bin_dir = join(root_directory, 'bin')
        conf.set('git_askpass_exe', join(bin_dir, 'git_askpass.sh'))
        conf.set('git_ssh_exe', join(bin_dir, 'git_ssh.sh'))

        # How slaves get the project
        # Slaves would get the project from master if set to True. Otherwise it would just get the project in
        # the same way how the master gets the project.
        conf.set('get_project_from_master', True)

        # Should we have shallow or full clones of the repository?
        # The master must have full clones, as slaves fetch from the master, and one cannot fetch from a shallow clone.
        conf.set('shallow_clones', False)

    def configure_postload(self, conf):
        """
        After the clusterrunner.conf file has been loaded, generate the paths which descend from the base_directory
        :type conf: Configuration
        """
        base_directory = conf.get('base_directory')
        log_dir = join(base_directory, 'log')
        conf.set('log_dir', log_dir)

        conf.set('log_file', join(log_dir, conf.get('log_filename')))
        conf.set('eventlog_file', join(log_dir, conf.get('eventlog_filename')))

    def load_from_config_file(self, config, config_filename):
        """
        :type config: Configuration
        :param config_filename:  str
        """
        self._load_section_from_config_file(config, config_filename, BASE_CONFIG_FILE_SECTION)
        if self.CONFIG_FILE_SECTION:
            self._load_section_from_config_file(config, config_filename, self.CONFIG_FILE_SECTION)

    def _get_config_file_whitelisted_keys(self):
        """
        Return the list of keys that we allow to be specified in a config file. Subclasses can override this method but
        should in general append values to the list returned by their superclass.

        :rtype: list[str]
        """
        return [
            'secret',
            'base_directory',
            'log_level',
            'build_symlink_directory',
            'hostname',
            'slaves',
            'port',
            'num_executors',
            'master_hostname',
            'master_port',
            'log_filename',
            'max_log_file_size',
            'eventlog_filename',
            'git_strict_host_key_checking',
            'cors_allowed_origins_regex',
            'get_project_from_master',
        ]

    def _load_section_from_config_file(self, config, config_filename, section):
        """
        Load a config file and copy all the values in a particular section to the Configuration singleton
        :type config: Configuration
        :type config_filename: str
        :type section: str
        """
        try:
            config_parsed = ConfigFile(config_filename).read_config_from_disk()
        except FileNotFoundError:
            sample_filename = join(config.get('root_directory'), 'conf', 'default_clusterrunner.conf')
            fs.create_dir(config.get('base_directory'))
            shutil.copy(sample_filename, config_filename)
            chmod(config_filename, ConfigFile.CONFIG_FILE_MODE)
            config_parsed = ConfigFile(config_filename).read_config_from_disk()

        if section not in config_parsed:
            raise InvalidConfigError('The config file {} does not contain a [{}] section'
                                     .format(config_filename, section))

        clusterrunner_config = config_parsed[section]
        whitelisted_file_keys = self._get_config_file_whitelisted_keys()
        for key in clusterrunner_config:
            if key not in whitelisted_file_keys:
                raise InvalidConfigError('The config file contains an invalid key: {}'.format(key))
            value = clusterrunner_config[key]

            self._cast_and_set(key, value, config)

    def _cast_and_set(self, key, value, config):
        """
        :type key: str
        :type value: str
        :type config: Configuration
        """
        default_value = config.get(key)

        if isinstance(default_value, bool):  # bool is a subclass of int so should be checked first
            value_mapping = {'true': True, 'false': False}
            if not isinstance(value, str) and value.lower() not in value_mapping.keys():
                raise InvalidConfigError('The value for {} should be True or False, but it is "{}"'.format(key, value))
            config.set(key, value_mapping[value.lower()])

        elif isinstance(default_value, int):
            config.set(key, int(value))

        elif isinstance(default_value, list):
            # The ConfigObj library converts comma delimited strings to lists.  In the case on a single element, we
            # need to do the conversion ourselves.
            if not isinstance(value, list):
                value = [value]
            config.set(key, value)

        else:  # Could be str or NoneType, we assume it should be a str
            # Hacky: If the value starts with ~, we assume it's a path that needs to be expanded
            if value.startswith('~'):
                value = expanduser(value)
            config.set(key, value)


class InvalidConfigError(Exception):
    """
    An exception with the content of the configuration file.
    """
