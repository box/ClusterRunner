import os
import stat

from configobj import ConfigObj

from app.util import fs
from app.util.process_utils import is_windows


class ConfigFile(object):
    CONFIG_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR

    def __init__(self, filename):
        """
        :type filename: str
        """
        self._filename = filename

    def read_config_from_disk(self):
        """
        Parse an INI-style config file from disk.
        """
        if not os.path.isfile(self._filename):
            raise FileNotFoundError('Conf file {} does not exist'.format(self._filename))
        file_mode = stat.S_IMODE(os.stat(self._filename).st_mode)
        if not is_windows() and file_mode != self.CONFIG_FILE_MODE:
            raise PermissionError('The conf file {} has incorrect permissions, '
                                  'should be 0600 for security reasons'.format(self._filename))
        config_parsed = ConfigObj(self._filename)
        return config_parsed

    def write_value(self, name, value, section):
        """
        Update this file by writing a single value to a section of a configuration file.
        :type name: str
        :type value: str
        :type section: str
        """
        config_parsed = self.read_config_from_disk()
        config_parsed[section][name] = value
        self._write_config_to_disk(config_parsed)

    def _write_config_to_disk(self, config_parsed):
        """
        Write a data structure of parsed config values to disk in an INI-style format.
        :type config_parsed: ConfigObj
        """
        fs.create_dir(os.path.dirname(self._filename))
        config_parsed.write()
        os.chmod(self._filename, self.CONFIG_FILE_MODE)
