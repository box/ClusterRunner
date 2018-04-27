from app.util.conf.base_config_loader import BaseConfigLoader


class DeployConfigLoader(BaseConfigLoader):

    def configure_defaults(self, conf):
        """
        These are the worker configuration defaults. These values can override values in BaseConfigLoader.
        :type conf: Configuration
        """
        super().configure_defaults(conf)
        conf.set('log_filename', 'clusterrunner_deploy.log')
        conf.set('log_level', 'INFO')
