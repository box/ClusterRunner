from os.path import join

from app.util.conf.base_config_loader import BaseConfigLoader


class ManagerConfigLoader(BaseConfigLoader):

    CONFIG_FILE_SECTION = 'manager'

    def configure_defaults(self, conf):
        """
        This is the manager configuration. These values should override values in base_conf.py.

        :type conf: Configuration
        """
        super().configure_defaults(conf)
        conf.set('port', 43000)
        conf.set('log_filename', 'clusterrunner_manager.log')
        conf.set('eventlog_filename', 'eventlog_manager.log')
        conf.set('shallow_clones', False)

        # Default values for heartbeat configuration
        conf.set('unresponsive_workers_cleanup_interval', 600)

    def configure_postload(self, conf):
        """
        After the clusterrunner.conf file has been loaded, generate the manager-specific paths which descend from the
        base_directory.
        :type conf: Configuration
        """
        super().configure_postload(conf)
        base_directory = conf.get('base_directory')
        # where repos are cloned on the manager
        conf.set('repo_directory', join(base_directory, 'repos', 'manager'))
        # where the worker's result artifacts should be stored
        conf.set('artifact_directory', join(base_directory, 'artifacts'))

        log_dir = conf.get('log_dir')
        conf.set('log_file', join(log_dir, 'clusterrunner_manager.log'))
        conf.set('eventlog_file', join(log_dir, 'eventlog_manager.log'))
        # where to store results on the manager
        conf.set('results_directory', join(base_directory, 'results', 'manager'))
        conf.set('timings_directory', join(base_directory, 'timings', 'manager'))  # timing data
