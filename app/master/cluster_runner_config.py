import yaml

from app.master.job_config import JobConfig
from app.util import log


class ClusterRunnerConfig(object):
    """
    This class represents all of the ClusterRunner job definitions that live inside a single clusterrunner.yaml file.
    """
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
        """
        Validate the parsed yaml structure. This method raises on validation errors.

        If validation is successful, add the job configs to this class instance.

        :param config: The parsed yaml data
        :type config: dict
        """
        config = yaml.safe_load(self._raw_yaml_contents)

        if not isinstance(config, dict):
            raise ConfigParseError('The yaml config file could not be parsed to a dictionary')

        self._job_configs = {}

        for job_name, job_config_sections in config.items():
            self._job_configs[job_name] = JobConfig.construct_from_dict(job_name, job_config_sections)

        if len(self._job_configs) == 0:
            raise ConfigParseError('No jobs found in the config.')


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
