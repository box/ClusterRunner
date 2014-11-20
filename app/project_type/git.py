import os
import pexpect
import signal
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

    # pylint: disable=redefined-builtin
    # Disable "redefined-builtin" because renaming the "hash" parameter would be a breaking change.
    def __init__(self, url, build_project_directory='', project_directory='', remote='origin', branch='master',
                 hash=None, config=None, job_name=None, remote_files=None, shallow=False):
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
        :param shallow: When cloning a repo, should the clone be shallow?
        :type shallow: bool
        """
        super().__init__(config, job_name, remote_files)
        self._url = url
        self._remote = remote
        self._branch = branch
        self._hash = hash
        self._shallow = shallow

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
            depth_param = '--depth {}'.format(str(self.CLONE_DEPTH)) if self._shallow else ''
            clone_command = 'git clone {} {} {}'. format(depth_param, self._url, self._repo_directory)
            self._execute_git_remote_command(clone_command)

        fetch_command = 'git fetch {} {}'.format(self._remote, self._branch)
        self._execute_git_remote_command(fetch_command, self._repo_directory)

        commit_hash = self._hash or 'FETCH_HEAD'
        reset_command = 'git reset --hard {}'.format(commit_hash)
        self._execute_in_repo_and_raise_on_failure(reset_command, 'Could not reset Git repo.')

        self._execute_in_repo_and_raise_on_failure('git clean -dfx', 'Could not clean Git repo.')

    def _execute_in_repo_and_raise_on_failure(self, command, message):
        self._execute_and_raise_on_failure(command, message, self._repo_directory)

    def _execute_git_remote_command(self, command, cwd=None, timeout=10):
        """
        Execute git-related commands. This functionality is sequestered into its own method because an automated
        system such as ClusterRunner must deal with user-targeted prompts (such that ask for a username/password)
        deliberately and explicitly. This method will raise a RuntimeError in case of a prompt.

        :type command: str
        :type cwd: str|None
        :param timeout: the number of seconds to wait for expected prompts before assuming there will be no prompt
        :type timeout: int
        """
        child = pexpect.spawn(command, cwd=cwd)

        # Because it is possible to receive multiple prompts in any git remote operation, we have to call pexpect
        # multiple times. For example, the first prompt might be a known_hosts ssh check prompt, and the second
        # prompt can be a username/password authentication prompt. Without this loop, ClusterRunner may indefinitely
        # hang in such a scenario.
        while True:
            try:
                prompt_index = child.expect(
                    ['^User.*: ', '^Pass.*: ', '.*Are you sure you want to continue connecting.*'], timeout=timeout)

                # Prompt: User/Password
                if prompt_index == 0 or prompt_index == 1:
                    child.kill(signal.SIGKILL)
                    raise RuntimeError('Failed to retrieve from git remote due to a user/password prompt. '
                                       'Command: {}'.format(command))
                # Prompt: ssh known_hosts check
                elif prompt_index == 2:
                    if Configuration['git_strict_host_key_checking']:
                        child.kill(signal.SIGKILL)
                        raise RuntimeError('Failed to retrieve from git remote due to failed known_hosts check. '
                                           'Command: {}'.format(command))

                    # Automatically add hosts that aren't in the known_hosts file to the known_hosts file.
                    child.sendline('yes')
                    self._logger.info('Automatically added a host to known_hosts in command: {}'.format(command))
            except pexpect.EOF:
                break
            except pexpect.TIMEOUT:
                self._logger.info('Command [{}] had no expected prompts after {} seconds.'.format(command, timeout))
                break

        # Dump out the output stream from pexpect just in case there was an unexpected prompt that wasn't caught.
        self._logger.debug("Output from command [{}] after {} seconds: {}".format(command, timeout, child.before))

        # The timeout here is set to None because we do not want a timeout of any sort--In the case that command
        # is a git clone, this call could potentially run for several minutes. We assume that by the time
        # code has reached this line (when it has exceeded the timeout value specified in the child.expect call
        # above) that if we were going to get prompted, we would have seen the prompts already.
        child.expect(pexpect.EOF, timeout=None)
        # This call is necessary for the child.exitstatus to be set properly. Otherwise, it can be set to None.
        child.close()

        if child.exitstatus != 0:
            raise RuntimeError('Git command failed. Child exit status: {}. Command: {}\nOutput: {}'.format(
                child.exitstatus, command, child.before.decode('utf-8', errors='replace')))

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
