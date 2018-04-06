from os.path import join

from app.util.conf.base_config_loader import BaseConfigLoader


class SlaveConfigLoader(BaseConfigLoader):

    CONFIG_FILE_SECTION = 'slave'

    def configure_defaults(self, conf):
        """
        These are the slave configuration defaults. These values can override values in BaseConfigLoader.
        :type conf: Configuration
        """
        super().configure_defaults(conf)
        conf.set('port', 43001)
        conf.set('num_executors', 1)
        conf.set('log_filename', 'clusterrunner_slave.log')
        conf.set('eventlog_filename', 'eventlog_slave.log')
        conf.set('master_hostname', 'localhost')
        conf.set('master_port', 43000)
        conf.set('shallow_clones', True)
        # Use a longer timeout for slaves since we don't yet have request metrics on the slave side and since
        # slaves are more likely to encounter long response times on the master due to the master being a
        # centralized hub with a single-threaded server.
        conf.set('default_http_timeout', 120)

        # Default values for heartbeat configuration
        conf.set('heartbeat_interval', 60)
        conf.set('heartbeat_failure_threshold', 10)

    def configure_postload(self, conf):
        """
        After the clusterrunner.conf file has been loaded, generate the slave-specific paths which descend from the
        base_directory.
        :type conf: Configuration
        """
        super().configure_postload(conf)
        base_directory = conf.get('base_directory')
        # where repos are cloned on the slave
        conf.set('repo_directory', join(base_directory, 'repos', 'slave'))
        # where the slave's result artifacts should be stored
        conf.set('artifact_directory', join(base_directory, 'artifacts'))
        # where to store results on the slave
        conf.set('results_directory', join(base_directory, 'results', 'slave'))
        conf.set('timings_directory', join(base_directory, 'timings', 'master'))  # timing data
