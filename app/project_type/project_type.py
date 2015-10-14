from collections import OrderedDict, namedtuple
import inspect
import os
import re
import signal
from subprocess import TimeoutExpired, STDOUT
from tempfile import TemporaryFile
from threading import Event
import time

from app.master.cluster_runner_config import ClusterRunnerConfig
from app.master.job_config import JobConfig
from app.util import log
from app.util.conf.configuration import Configuration
from app.util.process_utils import Popen_with_delayed_expansion, get_environment_variable_setter_command


class ProjectType(object):

    def __init__(self, config=None, job_name=None, remote_files=None, atoms_override=None):
        """
        :param config: A dictionary containing the job configuration for a single clusterrunner job, with the
            top-level keys being 'commands', 'atomizers', etc.
        :type config: dict | None
        :type job_name: str | None
        :param remote_files: key-value pairs of where the key is the output_file and the value is the url
        :type remote_files: dict[str, str] | None
        :param atoms_override: the list of overriden atoms specified from the build request. If this parameter
            is specified, then the atomization step is skipped.
        :type atoms_override: list[str]
        """
        self.project_directory = ''
        self._atoms_override = atoms_override
        self._config = config
        self._job_name = job_name
        self._remote_files = remote_files if remote_files else {}
        self._logger = log.get_logger(__name__)
        self._kill_event = Event()
        self._job_config = None

    @property
    def atoms_override(self):
        """
        :return: The list of atom command strings that were specified in the build request. This is an optional
            build request parameter that is defaulted to 'None', in which case atomization still occurs during
            build preparation.
        :rtype: list[str]|None
        """
        return self._atoms_override

    @property
    def job_name(self):
        return self._job_name

    def slave_param_overrides(self):
        """
        Produce a set of values to override original project type params for use on a slave machine. Override in
        subclasses to enable slave-specific behavior.

        :return: A set of values to override original project type params
        :rtype: dict[str, str]
        """
        return {}

    def job_config(self):
        """
        Return the job config found in this project_type and matching any job_name parameter passed in
        :rtype: JobConfig
        """
        if not self._job_config:
            # If the config was specified in the POST request, then there is no need to parse clusterrunner.yaml
            if self._config is not None:
                self._job_config = JobConfig.construct_from_dict(self._job_name, self._config)
                return self._job_config

            # Get job configuration from clusterrunner.yaml in repo.
            config = ClusterRunnerConfig(self._get_clusterrunner_config_file_contents())
            self._job_config = config.get_job_config(self._job_name)

        return self._job_config

    def _get_clusterrunner_config_file_contents(self):
        """
        Method for retrieving the contents of clusterrunner.yaml. Override this in project types using a different
        method.

        :return: The contents of clusterrunner.yaml
        :rtype: str
        """
        yaml_file = os.path.join(self.project_directory, Configuration['project_yaml_filename'])
        if not os.path.exists(yaml_file):
            raise FileNotFoundError('Could not find project yaml file {}'.format(yaml_file))

        with open(yaml_file, 'r') as f:
            config_contents = f.read()
        return config_contents

    def fetch_project(self):
        """
        Fetch the project onto the local machine.

        Runs once per machine per build. Runs the project_type's retrieve command (fetch, reset, etc) and produces
        a list of per-executor project_types.
        """
        self._fetch_project()
        self._logger.info('Build setup complete.')

        if self._remote_files:
            self._run_remote_file_setup()

    def _fetch_project(self):
        raise NotImplementedError

    def _execute_and_raise_on_failure(self, command, message, cwd=None, env_vars=None):
        """
        :rtype: string
        """
        output, exit_code = self.execute_command_in_project(command, cwd=cwd, extra_environment_vars=env_vars)
        # If the command was intentionally killed, do not raise an error
        if exit_code != 0 and not self._kill_event.is_set():
            raise RuntimeError('{} Command: "{}"\nOutput: "{}"'.format(message, command, output))
        return output

    def _execute_in_project_and_raise_on_failure(self, command, message):
        """
        :rtype: string
        """
        return self._execute_and_raise_on_failure(command, message, self.project_directory)

    def teardown_build(self, timeout=None):
        """
        Teardown the build on the local machine. This should run once per slave per build.

        :param timeout: A maximum number of seconds before the teardown command is terminated, or None for no timeout
        :type timeout: int | None
        """
        self.run_job_config_teardown(timeout=timeout)
        self._logger.info('ProjectType teardown complete.')

    def run_job_config_setup(self):
        """
        Execute any setup commands defined in the job config.
        """
        job_config = self.job_config()
        if job_config.setup_build:
            output, exit_code = self.execute_command_in_project(job_config.setup_build)
            if exit_code != 0:
                raise SetupFailureError('Build setup failed!\nCommand:\n"{}"\n\nOutput:\n{}'
                                        .format(job_config.setup_build, output))
            self._logger.info('Build setup completed successfully.')

    def run_job_config_teardown(self, timeout=None):
        """
        Execute any teardown commands defined in the job config.

        :param timeout: A maximum number of seconds before the teardown command is terminated, or None for no timeout
        :type timeout: int | None
        """
        job_config = self.job_config()
        if job_config.teardown_build:
            output, exit_code = self.execute_command_in_project(job_config.teardown_build, timeout=timeout)
            if exit_code != 0:
                raise TeardownFailureError('Build teardown failed!\nCommand:\n"{}"\n\nOutput:\n{}'
                                           .format(job_config.teardown_build, output))
            self._logger.info('Build teardown completed successfully.')

    def setup_executor(self):
        """
        Do setup for each executor. This should be called by client code for each executor before
        executing repeated commands in the project_type. Default implementation is to do nothing.
        """
        pass

    def teardown_executor(self):
        """
        Do cleanup for each executor. This should be called by client code if project_type.fetch_project()
        was called. Default implementation is to do nothing.
        """
        pass

    def command_in_project(self, command):
        """
        Do things like quote escaping, command prepending, postpending, etc.

        Most project types won't need to do anything to this method, so the default implementation
        is to just return the same command string.

        :param command: the shell command that would normally be executed directly in the shell
        :type command: string
        :return: the shell command that will be executed directly in the shell in order to run
            command in this project_type
        :rtype: string
        """
        return command

    def execute_command_in_project(self, command, extra_environment_vars=None, timeout=None, output_file=None,
                                   **popen_kwargs):
        """
        Execute a command in the context of the project

        :param command: the shell command to execute
        :type command: string
        :param extra_environment_vars: additional environment variables to set for command execution
        :type extra_environment_vars: dict[str, str]
        :param timeout: A maximum number of seconds before the process is terminated, or None for no timeout
        :type timeout: int | None
        :param output_file: The file to write console output to (both stdout and stderr). If not specified,
                            will generate a TemporaryFile. This method will close the file.
        :type output_file: BufferedRandom | None
        :param popen_kwargs: additional keyword arguments to pass through to subprocess.Popen
        :type popen_kwargs: dict[str, mixed]
        :return: a tuple of (the string output from the command, the exit code of the command)
        :rtype: (string, int)
        """
        environment_setter = self.shell_environment_command(extra_environment_vars)
        command = self.command_in_project('{} {}'.format(environment_setter, command))
        self._logger.debug('Executing command in project: {}', command)

        # Redirect output to files instead of using pipes to avoid: https://github.com/box/ClusterRunner/issues/57
        output_file = output_file if output_file is not None else TemporaryFile()
        pipe = Popen_with_delayed_expansion(
            command,
            shell=True,
            stdout=output_file,
            stderr=STDOUT,  # Redirect stderr to stdout, as we do not care to distinguish the two.
            start_new_session=True,  # Starts a new process group (so we can kill it without killing clusterrunner).
            **popen_kwargs
        )

        clusterrunner_error_msgs = self._wait_for_pipe_to_close(pipe, command, timeout)
        console_output = self._read_file_contents_and_close(output_file)
        exit_code = pipe.returncode

        if exit_code != 0:
            max_log_length = 300
            logged_console_output = console_output
            if len(console_output) > max_log_length:
                logged_console_output = '{}... (total output length: {})'.format(console_output[:max_log_length],
                                                                                 len(console_output))

            # Note we are intentionally not logging at error or warning level here. Interpreting a non-zero return
            # code as a failure is context-dependent, so we can't make that determination here.
            self._logger.notice(
                'Command exited with non-zero exit code.\nCommand: {}\nExit code: {}\nConsole output: {}\n',
                command, exit_code, logged_console_output)
        else:
            self._logger.debug('Command completed with exit code {}.', exit_code)

        exit_code = exit_code if exit_code is not None else -1  # Make sure we always return an int.
        combined_command_output = '\n'.join([console_output] + clusterrunner_error_msgs)
        return combined_command_output, exit_code

    def _wait_for_pipe_to_close(self, pipe, command, timeout):
        """
        Wait for the pipe to close (after command completes) or until timeout. If timeout is reached, then
        kill the pipe as well as any child processes spawned.

        :type pipe: Popen
        :type command: str
        :type timeout: int | None
        :return: the list of error encountered while waiting for the pipe to close.
        :rtype: list[str]
        """
        clusterrunner_error_msgs = []
        command_completed = False
        timeout_time = time.time() + (timeout or float('inf'))

        # Wait for the command to complete, but also periodically check the kill event flag to see if we should
        # terminate the process prematurely.
        while not command_completed and not self._kill_event.is_set() and time.time() < timeout_time:
            try:
                pipe.wait(timeout=1)
                command_completed = True  # wait() didn't raise TimeoutExpired, so process has finished executing.
            except TimeoutExpired:
                continue
            except Exception as ex:  # pylint: disable=broad-except
                error_message = 'Exception while waiting for process to finish.'
                self._logger.exception(error_message)
                clusterrunner_error_msgs.append(
                    'ClusterRunner: {} ({}: "{}")'.format(error_message, type(ex).__name__, ex))
                break

        if not command_completed:
            # We've been signaled to terminate subprocesses, so terminate them. But we still collect stdout and stderr.
            # We must kill the entire process group since shell=True launches 'sh -c "cmd"' and just killing the pid
            # will kill only "sh" and not its child processes.
            # Note: We may lose buffered output from the subprocess that hasn't been flushed before termination.
            self._logger.warning('Terminating PID: {}, Command: "{}"', pipe.pid, command)
            try:
                # todo: os.killpg sends a SIGTERM to all processes in the process group. If the immediate child process
                # ("sh") dies but its child processes do not, we will leave them running orphaned.
                try:
                    os.killpg(pipe.pid, signal.SIGTERM)
                except AttributeError:
                    self._logger.warning('os.killpg is not available. This is expected if ClusterRunner is running'
                                         'on Windows. Using os.kill instead.')
                    os.kill(pipe.pid, signal.SIGTERM)
            except (PermissionError, ProcessLookupError) as ex:  # os.killpg will raise if process has already ended
                self._logger.warning('Attempted to kill process group (pgid: {}) but raised {}: "{}".',
                                     pipe.pid, type(ex).__name__, ex)
            try:
                pipe.wait()
            except Exception as ex:  # pylint: disable=broad-except
                error_message = 'Exception while waiting for terminated process to finish.'
                self._logger.exception(error_message)
                clusterrunner_error_msgs.append(
                    'ClusterRunner: {} ({}: "{}")'.format(error_message, type(ex).__name__, ex))

        return clusterrunner_error_msgs

    def _read_file_contents_and_close(self, file):
        """
        :type file: BufferedRandom
        """
        file.seek(0)  # Reset file positions so we are reading from the beginning.
        contents = file.read().decode('utf-8', errors='replace')
        file.close()
        return contents

    def echo_command_in_project(self, command, *args, **kwargs):
        """
        Resolve the project_type vars in a command and echo the final result.
        :type command: str
        :rtype: (str, int)
        """
        echo_command = 'echo "{}"'.format(command.replace('"', '\\"'))
        return self.execute_command_in_project(echo_command, *args, **kwargs)

    def timing_file_path(self, job_name):
        """
        Get the path to the timing data file for a given job.

        :type job_name: str
        :return: the absolute path to where the timing file for job_name SHOULD be. This method does not guarantee
            that the timing file exists.
        :rtype: string
        """
        raise NotImplementedError

    def _get_environment_vars(self):
        return {'PROJECT_DIR': self.project_directory}

    def shell_environment_command(self, extra_environment_vars=None):
        """
        Turn a dict of environment vars into a shell string
        :param extra_environment_vars:
        :type extra_environment_vars: dict [string, string]
        :return: shell command for setting the environment
        :rtype: string
        """
        environment_vars = self._get_environment_vars()
        environment_vars.update(extra_environment_vars or {})

        commands = [get_environment_variable_setter_command(key, value) for key, value in environment_vars.items()]
        return ' '.join(commands)

    def kill_subprocesses(self):
        """
        Signal the environment that any currently running subprocesses should be terminated.
        """
        self._kill_event.set()

    @classmethod
    def required_constructor_argument_names(cls):
        """
        Get the list of required constructor argument names via introspection. E.g., if the __init__ signature is:
            def __init__(self, name, worth, happiness=20, loathing=True): ...

        then this method will return:
            ['name', 'worth']

        Subclasses should override this method if they want to decouple the list of required arguements from the
        __init__ signature.

        :return: A list of names of any required arguments to this class' constructor
        :rtype: list[str]
        """
        arguments_info = cls.constructor_arguments_info()
        return [arg_name for arg_name, arg_info in arguments_info.items() if arg_info.required]

    @classmethod
    def constructor_arguments_info(cls, blacklist=None):
        """
        Get info on the constructor arguments. This is used to expose documentation on parameters via both API error
        messages and command line help output.
        :param blacklist: blacklist of constructor arguments to omit.
        :type blacklist: list[str] | None
        :return: A mapping of the form:
        {
            'argument_name': {
                'help': first line of the argument docstring (everything after ":param argument_name: ")
                'required': True if constructor argument is required else False
                'default': default value of the argument if argument is not required
            },
            ...
        }
        :rtype: dict[str, _ProjectTypeArgumentInfo]
        """
        constructor_doc = inspect.getdoc(cls.__init__) or ''
        arg_spec = inspect.getfullargspec(cls.__init__)
        blacklist = blacklist or []
        argument_names = arg_spec.args[1:]  # discard "self", which is the first argument.
        default_arg_values = arg_spec.defaults or []
        num_required_args = len(argument_names) - len(default_arg_values)

        arguments_info = OrderedDict()
        for argument_index, argument_name in enumerate(argument_names):
            if argument_name in blacklist:
                continue
            # extract the doc for this param from the docstring. note: this only grabs the first line, so we can add
            # "private" additional doc on following lines.
            docstring_match = re.search(r'^\s*:param ' + argument_name + ': (.*)$', constructor_doc, re.MULTILINE)
            help_string = docstring_match.group(1) if docstring_match else None

            # determine if argument is required. if it's not required, also get its default argument value.
            is_required = argument_index < num_required_args
            default_value = None if is_required else default_arg_values[argument_index - num_required_args]

            arguments_info[argument_name] = _ProjectTypeArgumentInfo(
                help=help_string,
                required=is_required,
                default=default_value,
            )

        return arguments_info

    def project_id(self):
        """
        Get a string that uniquely identifies the project involved.  Build requests for the same project will have
        their own serial request handler.  This allows us to parallelize the atomization of builds which are for
        different projects (since their fetching and atomization commands will not collide).
        :return: string
        """
        raise NotImplementedError

    def _run_remote_file_setup(self):
        """
        Fetches remote files
        """
        for command in self._remote_file_commands():
            output, exit_code = self.execute_command_in_project(command)
            if exit_code != 0:
                raise RuntimeError('Remote file setup exited with {} while running `{}`'.format(exit_code, command))

    def _remote_file_commands(self):
        """
        :return: the command for downloading a remote resource and saving it to a specified
            output file
        :rtype: string
        """
        return ['curl {} -o $PROJECT_DIR/{}'.format(url, name) for (name, url) in self._remote_files.items()]


_ProjectTypeArgumentInfo = namedtuple('_ProjectTypeArgumentInfo', ['help', 'required', 'default'])


class SetupFailureError(Exception):
    pass


class TeardownFailureError(Exception):
    pass
