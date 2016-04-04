from os.path import join

from app.util.conf.base_config_loader import BaseConfigLoader


class MasterConfigLoader(BaseConfigLoader):

    CONFIG_FILE_SECTION = 'master'

    def configure_defaults(self, conf):
        """
        This is the master configuration. These values should override values in base_conf.py.

        :type conf: Configuration
        """
        super().configure_defaults(conf)
        conf.set('port', 43000)
        conf.set('log_filename', 'clusterrunner_master.log')
        conf.set('eventlog_filename', 'eventlog_master.log')
        conf.set('shallow_clones', False)

    def configure_postload(self, conf):
        """
        After the clusterrunner.conf file has been loaded, generate the master-specific paths which descend from the
        base_directory.
        :type conf: Configuration
        """
        super().configure_postload(conf)
        base_directory = conf.get('base_directory')
        # where repos are cloned on the master
        conf.set('repo_directory', join(base_directory, 'repos', 'master'))
        # where the slave's result artifacts should be stored
        conf.set('artifact_directory', join(base_directory, 'artifacts'))

        log_dir = conf.get('log_dir')
        conf.set('log_file', join(log_dir, 'clusterrunner_master.log'))
        conf.set('eventlog_file', join(log_dir, 'eventlog_master.log'))
        # where to store results on the master
        conf.set('results_directory', join(base_directory, 'results', 'master'))
        conf.set('timings_directory', join(base_directory, 'timings', 'master'))  # timing data
