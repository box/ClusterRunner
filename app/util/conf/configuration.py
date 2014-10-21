from app.util.singleton import Singleton


class _ConfigurationMetaclass(type):
    """
    Metaclass for Configuration class to allow keyed access on the singleton instance
    """
    def __getitem__(cls, item):
        configuration = Configuration.singleton()
        return configuration.get(item)

    def __setitem__(cls, key, value):
        configuration = Configuration.singleton()
        configuration.set(key, value)

    def __contains__(cls, key):
        configuration = Configuration.singleton()
        return key in configuration.properties


class Configuration(Singleton, metaclass=_ConfigurationMetaclass):
    """
    The main singleton configuration class -- the default configuration is in conf.base_conf

    Access configuration settings using configuration keys:
    >>> app_name = Configuration['name']
    """

    def __init__(self, as_instance=False):
        """
        :param as_instance: should this be instantiated as an instance variable?
        :type as_instance: bool
        :return:
        """
        if not as_instance:
            super().__init__()
        self.properties = {}

    def set(self, name, value):
        self.properties[name] = value
        return self

    def get(self, name):
        return self.properties[name]


