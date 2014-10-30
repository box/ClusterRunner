import os
import pexpect
from urllib.parse import urlparse

from app.util import fs
from app.project_type.project_type import ProjectType
from app.util.conf.configuration import Configuration


class Git(ProjectType):
    """
    Example API call to invoke a git-type build.
    {
        "type": "git",
        "url": "https://github.com/box/StatusWolf.git",
    }
    """

    CLONE_DEPTH = 50

    def __init__(self, url, build_project_directory='', project_directory='', remote='origin', branch='master',
                 hash=None, config=None, job_name=None, remote_files=None):
        """
        Note: the first line of each parameter docstring will be exposed as command line argument documentation for the
        clusterrunner build client.

        :param url: url to the git repo (ie: https, ssh)
        :type url: str
        :param build_project_directory: the symlinked directory of where PROJECT_DIR should end up being set to
        :type build_project_directory: str
        :param project_directory: path within the repo that contains cluster_runner.yaml
        :type project_directory: str
        :param remote: The git remote name to fetch from
        :type remote: str
        :param branch: The git branch name on the remote to fetch
        :type branch: str
        :param hash: The hash to reset hard on. If both hash and branch are set, we only use the hash.
        :type hash: str
        :param config: a yaml string representing the project_type's config
        :type config: str|None
        :param job_name: a list of job names we intend to run
        :type job_name: list [str] | None
        :param remote_files: dictionary mapping of output file to URL
        :type remote_files: dict[str, str] | None
        """
        super().__init__(config, job_name, remote_files)
        self._url = url
        self._remote = remote
        self._branch = branch
        self._hash = hash

        url_components = urlparse(url)
        url_full_path_parts = url_components.path.split('/')
        repo_name = url_full_path_parts[-1].split('.')[0]
        url_folder_path_parts = url_full_path_parts[:-1]
        repo_directory = os.path.join(Configuration['repo_directory'], url_components.netloc, *url_folder_path_parts)
        self._repo_directory = os.path.join(repo_directory, repo_name)
        self._timing_file_directory = os.path.join(
            Configuration['timings_directory'],
            url_components.netloc,
            url_components.path.strip('/')
        )

        # We explicitly set the repo directory to 700 so we don't inadvertently expose the repo to access by other users
        fs.create_dir(self._repo_directory, 0o700)
        fs.create_dir(self._timing_file_directory, 0o700)
        fs.create_dir(os.path.dirname(build_project_directory))

        # Create a symlink from the generated build project directory to the actual project directory.
        # This is done in order to switch between the master's and the slave's copies of the repo while not
        # having to do something hacky in order to user the master's generated atoms on the slaves.
        actual_project_directory = os.path.join(self._repo_directory, project_directory)

        try:
            os.unlink(build_project_directory)
        except FileNotFoundError:
            pass

        os.symlink(actual_project_directory, build_project_directory)
        self.project_directory = build_project_directory

    def _setup_build(self):
        """
        Clones the project if necessary, fetches from the remote repo and resets to the requested commit
        """
        _, exit_code = self.execute_command_in_project('git rev-parse', cwd=self._repo_directory)
        if exit_code != 0:  # This is not a git repo yet, we have to clone the project.
            clone_command = 'git clone --depth {} {} {}'. format(str(self.CLONE_DEPTH), self._url, self._repo_directory)
            self._execute_git_remote_command(clone_command)

        fetch_command = 'git fetch {} {}'.format(self._remote, self._branch)
        self._execute_git_remote_command(fetch_command, self._repo_directory)

        commit_hash = self._hash or 'FETCH_HEAD'
        reset_command = 'git reset --hard {}'.format(commit_hash)
        self._execute_in_repo_and_raise_on_failure(reset_command, 'Could not reset Git repo.')

        self._execute_in_repo_and_raise_on_failure('git clean -dfx', 'Could not clean Git repo.')

    def _execute_in_repo_and_raise_on_failure(self, command, message):
        self._execute_and_raise_on_failure(command, message, self._repo_directory)

    def _execute_git_remote_command(self, command, cwd=None, timeout=None):
        """
        Execute git-related commands. This functionality is sequestered into its own method because an automated
        system such as ClusterRunner must deal with user-targeted prompts (such that ask for a username/password)
        deliberately and explicitly. This method will raise a RuntimeError in case of a prompt.

        :type command: str
        :type cwd: str|None
        :param timeout: the number of seconds to wait before throwing an exception. If set to None, no timeout.
        :type timeout: int|None
        """
        try:
            child = pexpect.spawn(command, cwd=cwd, timeout=timeout)
        except pexpect.TIMEOUT:
            child.kill(0)
            raise RuntimeError('Command [{}] timed out with output: {}'.format(command, "\n".join(child.readlines())))

        try:
            prompt_index = child.expect(['^User.*: ', '^Pass.*: ', '.*Are you sure you want to continue connecting.*'])

            if prompt_index is not None:
                child.kill(0)

            if prompt_index == 0 or prompt_index == 1:
                raise RuntimeError('Failed to retrieve from git remote due to a user/password prompt. '
                                   'Command: {}'.format(command))
            elif prompt_index == 2:
                raise RuntimeError('Failed to retrieve from git remote due to a ssh known_hosts key prompt. '
                                   'Command: {}'.format(command))

        except pexpect.EOF:
            pass
        child.expect(pexpect.EOF)
        if child.exitstatus != 0:
            raise RuntimeError('Git command failed.  Command: {}\nOutput: {}'.format(command,
                                                                                     child.before.decode('utf-8')))

    def execute_command_in_project(self, *args, **kwargs):
        """
        Execute a command inside the repo. See superclass for parameter documentation.
        """
        # There is a scenario where self.project_directory doesn't exist yet (when a certain repo has never been
        # fetched before on this particular machine). In order to avoid having python barf during this scenario,
        # we have only pass in the cwd if it exists.
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.project_directory if os.path.exists(self.project_directory) else None
        return super().execute_command_in_project(*args, **kwargs)

    def timing_file_path(self, job_name):
        """
        :type job_name: str
        :return: the absolute path to where the timing file for job_name SHOULD be. This method does not guarantee
            that the timing file exists.
        :rtype: string
        """
        return os.path.join(self._timing_file_directory, "{}.timing.json".format(job_name))
