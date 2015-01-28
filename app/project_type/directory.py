import os
from platform import node

from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration
from app.util.log import get_logger


class Directory(ProjectType):
    """
    Example API call to invoke a directory-type build.
    {
        "type": "directory",
        "project_directory": "examples/directory job",
    }
    """
    def __init__(self, project_directory, config=None, job_name=None, build_project_directory=None,
                 remote_files=None):
        """
        Note: the first line of each parameter docstring will be exposed as command line argument documentation for the
        clusterrunner build client.

        :param project_directory: path to the directory that contains the project and cluster_runner.yaml
        :type project_directory: string
        :param config: a yaml string to be used in place of a cluster_runner.yaml
        :type config: string|None
        :param job_name: a list of job names we intend to run
        :type job_name: list [str] | None
        :param remote_files: dictionary mapping of output file to URL
        :type remote_files: dict[str, str] | None
        """
        super().__init__(config, job_name, remote_files)
        self._logger = get_logger(__name__)
        self.project_directory = os.path.abspath(project_directory)
        self._logger.debug('Project directory is {}'.format(project_directory))

    def _fetch_project(self):
        check_command = 'test -d "{}"'.format(self.project_directory)
        output, exit_code = self.execute_command_in_project(check_command, cwd='/')
        if exit_code != 0:
            raise RuntimeError('Could not find the directory "{}" on {}. Directory build mode is not supported on '
                               'clusters with remote slaves.'.format(self.project_directory, node()))

    def execute_command_in_project(self, *args, **kwargs):
        """
        Execute a command inside the directory. See superclass for parameter documentation.
        """
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.project_directory
        return super().execute_command_in_project(*args, **kwargs)

    def timing_file_path(self, job_name):
        """
        :type job_name: str
        :return: the absolute path to where the timing file for job_name SHOULD be. This method does not guarantee
            that the timing file exists.
        :rtype: string
        """
        timings_subdirectory = os.path.splitdrive(self.project_directory)[1][1:]  # cut off mount point and leading '/'
        return os.path.join(
            Configuration['timings_directory'],
            timings_subdirectory,
            '{}.timing.json'.format(job_name)
        )

    def project_id(self):
        return self.project_directory
