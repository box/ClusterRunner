from multiprocessing import Manager, Pool  # pylint: disable=no-name-in-module
import os
import pexpect
import psutil
import queue
import shutil
import signal
from urllib.parse import urlparse

from app.project_type.project_type import ProjectType
from app.util import fs, log
from app.util.conf.configuration import Configuration
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class Git(ProjectType):
    """
    Example API call to invoke a git-type build.
    {
        "type": "git",
        "url": "https://github.com/box/StatusWolf.git",
    }
    """
    CLONE_DEPTH = 50
    DIRECTORY_PERMISSIONS = 0o700

    @classmethod
    def params_for_slave(cls, project_type_params):
        """
        Produces a modified set of project type params for use on a slave machine. We modify the repo url so the slave
        clones or fetches from the master directly. This should be faster than cloning/fetching from the original git
        remote.
        :param project_type_params: The parameters for creating an ProjectType instance -- the dict should include the
            'type' key, which specifies the ProjectType subclass name, and key/value pairs matching constructor
            arguments for that ProjectType subclass.
        :type project_type_params: dict
        :return: A modified set of project type params
        :rtype: dict
        """
        master_repo_path = cls.get_full_repo_directory(project_type_params['url'])
        master_repo_url = 'ssh://{}{}'.format(Configuration['hostname'], master_repo_path)
        project_type_params = project_type_params.copy()
        project_type_params['url'] = master_repo_url
        return project_type_params

    @staticmethod
    def get_full_repo_directory(url):
        """
        Generates a directory to house the repo based on the origin url
        :return: A path to clone the git repo in
        :rtype: str
        """
        url_components = urlparse(url)
        url_full_path_parts = url_components.path.split('/')
        repo_name = url_full_path_parts[-1].split('.')[0]
        url_folder_path_parts = url_full_path_parts[:-1]
        repo_directory = os.path.join(Configuration['repo_directory'], url_components.netloc, *url_folder_path_parts)
        return fs.remove_invalid_path_characters(os.path.join(repo_directory, repo_name))

    @staticmethod
    def get_timing_file_directory(url):
        """
        Generates the path to store timing results in
        :param url: The remote 'origin' url for the git repo
        :return: A path for storing timing files
        :rtype: str
        """
        url_components = urlparse(url)
        timings_directory = os.path.join(
            Configuration['timings_directory'],
            url_components.netloc,
            url_components.path.strip('/')
        )
        return fs.remove_invalid_path_characters(timings_directory)

    # pylint: disable=redefined-builtin
    # Disable "redefined-builtin" because renaming the "hash" parameter would be a breaking change.
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
        self._repo_directory = self.get_full_repo_directory(self._url)
        self._timing_file_directory = self.get_timing_file_directory(self._url)
        self._git_remote_command_executor = _GitRemoteCommandExecutor()

        # We explicitly set the repo directory to 700 so we don't inadvertently expose the repo to access by other users
        fs.create_dir(self._repo_directory, self.DIRECTORY_PERMISSIONS)
        fs.create_dir(self._timing_file_directory, self.DIRECTORY_PERMISSIONS)
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

    def _fetch_project(self):
        """
        Clones the project if necessary, fetches from the remote repo and resets to the requested commit
        """
        # For backward compatibility: If a shallow repo exists, delete it.  Shallow cloning is no longer supported,
        # it causes failures when fetching refs that depend on commits which are excluded from the shallow clone.
        existing_repo_is_shallow = os.path.isfile(os.path.join(self._repo_directory, '.git', 'shallow'))
        if existing_repo_is_shallow:
            if os.path.exists(self._repo_directory):
                shutil.rmtree(self._repo_directory)
                fs.create_dir(self._repo_directory, self.DIRECTORY_PERMISSIONS)

        # Clone the repo if it doesn't exist
        _, git_exit_code = self.execute_command_in_project('git rev-parse', cwd=self._repo_directory)
        repo_exists = git_exit_code == 0
        if not repo_exists:  # This is not a git repo yet, we have to clone the project.
            clone_command = 'git clone {} {}'. format(self._url, self._repo_directory)
            self._git_remote_command_executor.execute(clone_command)

        # Must add the --update-head-ok in the scenario that the current branch of the working directory
        # is equal to self._branch, otherwise the git fetch will exit with a non-zero exit code.
        # Must specify the colon in 'branch:branch' so that the branch will be created locally. This is
        # important because it allows the slave hosts to do a git fetch from the master for this branch.
        fetch_command = 'git fetch --update-head-ok {0} {1}:{1}'.format(self._remote, self._branch)
        self._git_remote_command_executor.execute(fetch_command, cwd=self._repo_directory)

        commit_hash = self._hash or 'FETCH_HEAD'

        # The '--' option acts as a delimiter to differentiate values that can be "tree-ish" or a "path"
        reset_command = 'git reset --hard {} --'.format(commit_hash)
        self._execute_in_repo_and_raise_on_failure(reset_command, 'Could not reset Git repo.')

        self._execute_in_repo_and_raise_on_failure('git clean -dfx', 'Could not clean Git repo.')

    def _execute_in_repo_and_raise_on_failure(self, command, message):
        self._execute_and_raise_on_failure(command, message, self._repo_directory)

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

    def project_id(self):
        return self._repo_directory


class _GitRemoteCommandExecutor(object):
    """
    This class is responsible for executing git commands that contact the repo's remote. We use the pexpect library here
    since git commands may prompt for user input and we want to intercept those prompts.

    We've moved the pexpect logic into a Python subprocess (using the multiprocessing library). This is to work around
    a shortcoming of pexpect where it will begin to raise exceptions once the Python process holds more than 1024 open
    files (which includes tcp connections, and those scale with the number of slaves connected to the master). Once]
    pexpect fixes this issue, we can move this logic back into the main process.
    The pexpect issue is tracked here: https://github.com/pexpect/pexpect/issues/47
    """
    def __init__(self):
        self._logger = log.get_logger(__name__)

    def execute(self, command, cwd=None, timeout=10):
        """
        Start the _execute_git_remote_command() method in a subprocess.
        :type command: str
        :type cwd: str | None
        :param timeout: the number of seconds to wait for expected prompts before assuming there will be no prompt
        :type timeout: int
        """
        # We use a multiprocessing.Pool here (instead of a Process) since the Pool can propagate any exceptions that
        # occur in the subprocess back to the main process.
        with Manager() as manager, Pool(processes=1) as pool:  # pylint: disable=not-callable
            # A queue is used to transfer log messages back to the main process instead of trying to log them from the
            # subprocess. This avoids issues around both processes potentially writing logs at the same time and
            # clobbering each other's log messages.
            log_msg_queue = manager.Queue()
            async_result = pool.apply_async(self._execute_git_remote_command_subprocess,
                                            args=(command, cwd, timeout, log_msg_queue))

            # While the subprocess is executing, watch for any logs it puts into the queue and log them immediately.
            while not async_result.ready() or not log_msg_queue.empty():
                try:
                    log_level, unformatted_msg, format_args = log_msg_queue.get(timeout=0.5)
                    self._logger.log(log_level, unformatted_msg, *format_args)
                except queue.Empty:
                    pass

            # If any exception occurred in the subprocess, a call to async_result.get() will reraise that exception.
            async_result.get()

    def _execute_git_remote_command_subprocess(self, *args, **kwargs):
        """
        This is the entry point for the subprocess that executes git remote commands using pexpect. Args and kwargs are
        passed directly through to self._execute_git_remote_command().
        """
        # Reset signal handlers -- unhandled exceptions will be handled by the main process when the subprocess dies.
        UnhandledExceptionHandler.reset_signal_handlers()
        self._close_unneeded_network_connections()
        self._execute_git_remote_command(*args, **kwargs)

    def _close_unneeded_network_connections(self):
        """
        This is called after forking a subprocess to reduce the number of open file descriptors of the child process.
        Since a forked child process inherits file descriptors from the parent, the child ends up with a bunch of
        unneeded fds. Doing this allows pexpect to use a low file descriptor number (since it raises an exception if
        using a file descriptor number greater than 1024.)
        """
        process = psutil.Process(os.getpid())
        fds_to_close = [connection.fd for connection in process.connections()]
        for fd_to_close in fds_to_close:
            try:
                os.close(fd_to_close)
            except OSError:
                pass

    def _execute_git_remote_command(self, command, cwd, timeout, log_msg_queue):
        """
        Execute git-related commands. This functionality is sequestered into its own method because an automated
        system such as ClusterRunner must deal with user-targeted prompts (such that ask for a username/password)
        deliberately and explicitly. This method will raise a RuntimeError in case of a prompt.

        :type command: str
        :type cwd: str|None
        :type timeout: int
        :type log_msg_queue: multiprocessing.queues.Queue
        """
        # todo: Reenable the functionality around listening for a kill_event to abort execution of this method. This
        # todo: has been temporarily disabled due to complexity around doing this between multiple processes.
        credentials_prompt_patterns = [
            r'^User.*:',
            r'^Pass.*:',
            r'(^|\n)\S+@\S+\'s password:',  # example prompt: "jharrington@jharrington.local's password: "
        ]
        ssh_host_check_patterns = [
            'Are you sure you want to continue connecting',
        ]
        patterns_to_expect = credentials_prompt_patterns + ssh_host_check_patterns
        do_strict_host_key_checking = Configuration['git_strict_host_key_checking']

        # Because it is possible to receive multiple prompts in any git remote operation, we have to call pexpect
        # multiple times. For example, the first prompt might be a known_hosts ssh check prompt, and the second
        # prompt can be a username/password authentication prompt. Without this loop, ClusterRunner may indefinitely
        # hang in such a scenario.
        child = pexpect.spawn(command, cwd=cwd)
        while True:
            try:
                prompt_index = child.expect(patterns_to_expect, timeout=timeout)
                matched_pattern = patterns_to_expect[prompt_index]

                if matched_pattern in credentials_prompt_patterns:
                    child.kill(signal.SIGKILL)
                    raise RuntimeError('Failed to retrieve from git remote due to a user/password prompt. '
                                       'Command: {}'.format(command))

                elif matched_pattern in ssh_host_check_patterns:
                    if do_strict_host_key_checking:
                        child.kill(signal.SIGKILL)
                        raise RuntimeError('Failed to retrieve from git remote due to failed known_hosts check. '
                                           'Command: {}'.format(command))

                    # Automatically add hosts that aren't in the known_hosts file to the known_hosts file.
                    child.sendline('yes')
                    log_msg_queue.put(
                        ('INFO', 'Automatically added a host to known_hosts in command: {}', (command,)))

            except pexpect.EOF:
                break
            except pexpect.TIMEOUT:
                log_msg_queue.put(
                    ('INFO', 'Command [{}] had no expected prompts after {} seconds.', (command, timeout)))
                break

        # Dump out the output stream from pexpect just in case there was an unexpected prompt that wasn't caught.
        log_msg_queue.put(
            ('DEBUG', 'Output from command [{}] after {} seconds: {}', (command, timeout, child.before)))

        # Now we assume we are past any prompts and wait for the command to end.  We need to keep checking
        # if the kill event has been set in case the build is canceled during setup.
        finished = None
        while finished is None:  # and not self._kill_event.is_set()  # todo: kill_event temporarily disabled
            try:
                finished = child.expect(pexpect.EOF, timeout=1)
            except pexpect.TIMEOUT:
                continue

        # This call is necessary for the child.exitstatus to be set properly. Otherwise, it can be set to None.
        child.close()

        # Raise an error on non-zero exit code (unless the command was intentionally killed).
        if child.exitstatus != 0:  # and not self._kill_event.is_set():  # todo: kill_event temporarily disabled
            raise RuntimeError('Git command failed. Child exit status: {}. Command: {}\nOutput: {}'.format(
                child.exitstatus, command, child.before.decode('utf-8', errors='replace')))
