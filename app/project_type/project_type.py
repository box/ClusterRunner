from collections import OrderedDict, namedtuple
import inspect
import os
import re
import signal
from subprocess import PIPE, Popen, TimeoutExpired
from threading import Event

from app.master.cluster_runner_config import ClusterRunnerConfig
from app.util import log
from app.util.conf.configuration import Configuration


class ProjectType(object):

    def __init__(self, config=None, job_name=None, remote_files=None):
        """
        :param config: A yaml string representing a cluster_runner.yaml file
        :type config: str | None
        :type job_name: str | None
        :param remote_files: key-value pairs of where the key is the output_file and the value is the url
        :type remote_files: dict[str, str] | None
        """
        self.project_directory = ''
        self._config = config
        self._job_name = job_name
        self._remote_files = remote_files if remote_files else {}

        self._logger = log.get_logger(__name__)
        self._kill_event = Event()

    def job_config(self):
        """
        Return the job config found in this project_type and matching any job_name parameter passed in
        :rtype: JobConfig
        """
        config = ClusterRunnerConfig(self._get_config_contents())
        return config.get_job_config(self._job_name)

    def _get_config_contents(self):
        """
        Default method for retriving the contents of cluster_runner.yaml.  Override this in project types using a
        different method
        :return: The contents of cluster_runner.yaml
        :rtype: str
        """
        if self._config is not None:
            return self._config

        yaml_file = os.path.join(self.project_directory, Configuration['project_yaml_filename'])
        if not os.path.exists(yaml_file):
            raise FileNotFoundError('Could not find project yaml file {}'.format(yaml_file))

        with open(yaml_file, 'r') as f:
            config_contents = f.read()
        return config_contents

    def setup_build(self, executors=None, project_type_params=None):
        """
        Setup the project_type on the local machine.  Runs once per machine per build. Runs the project_type's
        retrieve command (fetch, reset, etc), produces a list of per-executor project_type, and runs any setup defined
        in the job config on each of those.

        :type executors: list [SubjobExecutor]
        :type project_type_params: dict [str, str]
        """
        if (executors is None) != (project_type_params is None):
            raise RuntimeError('setup_build called with invalid params, either both executors and project_type_params '
                               'should be set, or neither')

        self._setup_build()
        self._logger.info('Build setup complete.')

        if self._remote_files:
            self._run_remote_file_setup()

        # If executors were passed in, run configure_environment to do per-executor setup and any job config setup on
        # each one.
        if executors and project_type_params:
            self._setup_executors(executors, project_type_params)
        else:  # Otherwise, do any job config setup defined in this (main) project_type
            self.run_job_config_setup()

    def _setup_build(self):
        raise NotImplementedError

    def _execute_and_raise_on_failure(self, command, message, cwd=None):
        output, exit_code = self.execute_command_in_project(command, cwd=cwd)
        if exit_code != 0:
            raise RuntimeError('{} Command: "{}"\nOutput: "{}"'.format(message, command, output))

    def _execute_in_project_and_raise_on_failure(self, command, message):
        self._execute_and_raise_on_failure(command, message, self.project_directory)

    def teardown_build(self):
        """
        Teardown the build on the local machine.  Runs once per machine per build.
        """
        self.run_job_config_teardown()
        self._logger.info('ProjectType teardown complete.')
        # TODO: run _teardown_executors for each executor if this is a Docker project_type, like _setup_executors above

    def run_job_config_setup(self):
        """
        Execute any setup commands defined in the job config
        """
        job_config = self.job_config()
        if job_config.setup_build:
            output, exit_code = self.execute_command_in_project(job_config.setup_build)
            if exit_code != 0:
                raise RuntimeError('Job setup failed, cmd: {} -- output: {}'.format(job_config.setup_build,
                                                                                    output))
            self._logger.info('Job setup complete')

    def run_job_config_teardown(self):
        """
        Execute any teardown commands defined in the job config
        """
        job_config = self.job_config()
        if job_config.teardown_build:
            output, exit_code = self.execute_command_in_project(job_config.teardown_build)
            if exit_code != 0:
                raise RuntimeError('Job teardown failed, cmd: {} -- output: {}'.format(job_config.teardown_build,
                                                                                       output))
            self._logger.info('Job teardown complete')

    def _setup_executors(self, executors, project_type_params):
        """
        Given the executors, run the job config setup commands.  Override this to specify different behavior per
        project_type type
        :type executors: list [SubjobExecutor]
        :type project_type_params: dict [str, str]
        """
        for executor in executors:
            executor.configure_project_type(project_type_params)
        self.run_job_config_setup()

    def setup_executor(self):
        """
        Do setup for each executor. This should be called by client code for each executor before
        executing repeated commands in the project_type. Default implementation is to do nothing.
        """
        pass

    def teardown_executor(self):
        """
        Do cleanup for each executor. This should be called by client code if project_type.setup_build()
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

    def execute_command_in_project(self, command, extra_environment_vars=None, **popen_kwargs):
        """
        Execute a command in the context of the project

        :param command: the shell command to execute
        :type command: string
        :param extra_environment_vars: additional environment variables to set for command execution
        :type extra_environment_vars: dict[str, str]
        :param popen_kwargs: additional keyword arguments to pass through to subprocess.Popen
        :type popen_kwargs: dict[str, mixed]
        :return: a tuple of (the string output from the command, the exit code of the command)
        :rtype: (string, int)
        """
        environment_setter = self.shell_environment_command(extra_environment_vars)
        command = self.command_in_project('{} {}'.format(environment_setter, command))
        self._logger.debug('Executing command in project: {}', command)

        pipe = Popen(
            command,
            shell=True,
            stdout=PIPE,
            stderr=PIPE,
            start_new_session=True,  # Starts a new process group (so we can kill it without killing clusterrunner).
            **popen_kwargs
        )

        # Try waiting for the command to complete, but also periodically check an event flag to see if we should
        # terminate the process prematurely.
        output_raw, err_raw = None, None
        command_completed = False
        while not command_completed and not self._kill_event.is_set():
            try:
                output_raw, err_raw = pipe.communicate(timeout=1)  # pylint: disable=unexpected-keyword-arg
                command_completed = True  # communicate() didn't timeout, so process has finished executing.
            except TimeoutExpired:
                continue

        if not command_completed:
            # We've been signaled to terminate subprocesses, so terminate them. But we still collect stdout and stderr.
            # We must kill the entire process group since shell=True launches 'sh -c "cmd"' and just killing the pid
            # will kill only "sh" and not its child processes.
            self._logger.warning('Terminating PID: {}, Command: "{}"', pipe.pid, command)
            try:
                os.killpg(pipe.pid, signal.SIGTERM)
            except (PermissionError, ProcessLookupError) as ex:  # os.killpg will raise if process has already ended
                self._logger.warning('Attempted to kill process group (pgid: {}) but raised {}: {}.',
                                     pipe.pid, type(ex).__name__, ex)

            output_raw, err_raw = pipe.communicate()

        output = output_raw.decode('utf-8', errors='replace') if output_raw else ''
        err = err_raw.decode('utf-8', errors='replace') if err_raw else ''
        exit_code = pipe.returncode

        if exit_code != 0:
            max_log_length = 300
            logged_output, logged_err = output, err
            if len(output) > max_log_length:
                logged_output = '{}... (total stdout length: {})'.format(output[:max_log_length], len(output))
            if len(err) > max_log_length:
                logged_err = '{}... (total stderr length: {})'.format(err[:max_log_length], len(err))

            # Note we are intentionally not logging at error or warning level here. Interpreting a non-zero return code
            # as a failure is context-dependent, so we can't make that determination here.
            self._logger.notice(
                'Command exited with non-zero exit code.\nCommand: {}\nExit code: {}\nStdout: {}\nStderr: {}\n',
                command, exit_code, logged_output, logged_err
            )
        return '\n'.join([output, err]), exit_code

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

        commands = ['export {}="{}";'.format(key, value) for key, value in environment_vars.items()]
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
