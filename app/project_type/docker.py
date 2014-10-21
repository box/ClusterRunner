import os
import string

from app.project_type.docker_container import DockerContainer
from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration


class Docker(ProjectType):
    """
    Example API call to invoke a docker-type build.
    {
        "type": "docker",
        "image": "pod4101-automation1102.pod.box.net:5000/webapp_v5_dev:latest",
        "project_directory": "/box/www/current",
        "host": "pod4101-tester.dev.box.net",
        "user": "jenkins"
    }
    """

    def __init__(self, image, project_directory, mounted_volumes=None, user=None, host=None, config=None,
                 job_name=None, build_project_directory=None, remote_files=None):
        """
        Note: the first line of each parameter docstring will be exposed as command line argument documentation for the
        clusterrunner build client.

        :param image: url to the image with tag (ie: docker01.dev.box.net/webapp_v5dev:latest)
        :type image: string
        :param project_directory: path within the docker image that contains cluster_runner.yaml
        :type project_directory: string
        :param mounted_volumes: key-values of mounted host:container directories
        :type mounted_volumes: dict of [str, str]
        :param user: the user to run the container as
        :type user: string|None
        :param host: the hostname to assign for the container
        :type host: string|None
        :param config: a yaml string representing the project_type's config
        :type config: str|None
        :param job_name: a list of job names we intend to run
        :type job_name: list [str] | None
        :param remote_files: dictionary mapping of output file to URL
        :type remote_files: dict[str, str] | None
        """
        super().__init__(config, job_name, remote_files)
        self.project_directory = project_directory
        self._image = image

        artifact_dir = Configuration['artifact_directory']
        mounted_volumes = mounted_volumes or {}
        mounted_volumes.setdefault(artifact_dir, artifact_dir)

        self._container = DockerContainer(image, user, host, mounted_volumes)

    def _setup_build(self):
        pull_command = 'docker pull {}'.format(self._image)
        self._execute_in_project_and_raise_on_failure(pull_command, 'Could not pull Docker container.')

    def _get_config_contents(self):
        """
        Get the contents of cluster_runner.yaml from a Docker container
        :return: The contents of cluster_runner.yaml
        :rtype: str
        """
        yaml_path = os.path.join(self.project_directory, Configuration['project_yaml_filename'])
        raw_config_contents, _ = self.execute_command_in_project("cat " + yaml_path)

        if raw_config_contents is None:
            raise RuntimeError('Could not read {} from the Docker container'.format(yaml_path))

        return raw_config_contents

    def _setup_executors(self, executors, project_type_params):
        """
        Run the job config setup on each executor's project_type.  This override is necessary because a container is
        started for each executor, and the job config's setup command should run on each of them.
        :type executors: list [SubjobExecutor]
        :type project_type_params: dict [str, str]
        """
        super()._setup_executors(executors, project_type_params)
        for executor in executors:
            executor.run_job_config_setup()

    def execute_command_in_project(self, command, extra_environment_vars=None, **popen_kwargs):
        """
        Execute a command in the docker container. Starts a docker session

        :param command: the shell command to execute
        :type command: string
        :param extra_environment_vars: additional environment variables to set for command execution
        :type extra_environment_vars: dict[str, str]
        :param popen_kwargs: Note: this is unused in the docker project_type
        :type popen_kwargs: dict
        :return: a tuple of (the string output from the command, the exit code of the command)
        :rtype: (string, int)
        """
        environment_setter = self.shell_environment_command(extra_environment_vars)
        command = self.command_in_project('{} {}'.format(environment_setter, command))
        self._logger.debug('Executing command in project: {}', command)

        return self._container.run(command)

    def setup_executor(self):
        """
        Start a new docker session via which commands will be executed.
        """
        self._container.start_session()

    def teardown_executor(self):
        """
        Close the running docker session.
        """
        self._container.end_session()

    def timing_file_path(self, job_name):
        """
        :type job_name: str
        :return: the absolute path to where the timing file for job_name SHOULD be. This method does not guarantee
            that the timing file exists.
        :rtype: string
        """
        # There can be a colon in the URL part of the docker image, so we only want to check the image_and_tag
        # portion of the full docker image path for a colon (in order to strip out the tag).
        image_and_tag = self._image.rsplit('/', 1)[-1]

        if ':' in image_and_tag:
            full_image_without_tag = self._image.rsplit(':', 1)[0]
        else:
            full_image_without_tag = self._image

        file_system_friendly_docker_image = self._remove_file_system_unfriendly_characters(full_image_without_tag)
        return os.path.join(
            Configuration['timings_directory'],
            file_system_friendly_docker_image,
            "{}.timing.json".format(job_name)
        )

    def _remove_file_system_unfriendly_characters(self, unescaped_path):
        """
        Escape the string unescaped_path to be POSIX directory format compliant.

        :param unescaped_path: the original, unescaped string
        :type unescaped_path: string
        :rtype: string
        """
        valid_chars = "-_.()%s%s" % (string.ascii_letters, string.digits)
        return ''.join(c for c in unescaped_path if c in valid_chars)
