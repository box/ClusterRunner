import os
import subprocess
from tempfile import TemporaryDirectory
import time

from app.util import log


class DockerContainer(object):
    """
    Represents a docker container. Supports starting an interactive session.
    """
    def __init__(self, image, user=None, host=None, mounted_volumes=None):
        """
        :type image: str
        :type user: str
        :type host: str
        :type mounted_volumes: dict[str, str]
        """
        self._image = image
        self._user = user
        self._host = host
        self._mounted_volumes = mounted_volumes or {}
        self._active_session = None

    def pull(self):
        """
        Execute a docker pull for this container's image and block until finished. Returns whether or not the
        "docker pull" command exited successfully.

        :rtype: bool
        """
        pull_process = subprocess.Popen(['docker', 'pull', self._image], stdout=subprocess.DEVNULL)
        pull_process.communicate()
        return pull_process.returncode == 0

    def run(self, command_to_execute):
        """
        Do a "docker run" with the specified command and block until the command finishes. If an interactive session
        has been started by calling start_session(), then execute this command in that running session. Otherwise,
        start up a new container to run the command.

        :type command_to_execute: str
        :return: The output and exit code of the command run in the docker container.
        :rtype: (str, int)
        """
        if self._active_session:
            output, exit_code = self._active_session.execute(command_to_execute)

        else:
            escaped_command = command_to_execute.replace("'", "'\"'\"'")
            wrapped_command = "/bin/bash -c '{}'".format(escaped_command)
            docker_process = self._execute_docker_run(wrapped_command)

            output, _ = docker_process.communicate()
            exit_code = docker_process.returncode

        if type(output) is bytes:
            output = output.decode()

        return output, exit_code

    # todo: Defaulting the command to '/bin/bash' is probably not the most universal solution. We need to be able to
    # todo:   get a shell into the container, but may not want to override the CMD specified in a dockerfile.
    def _run_interactive(self, command_to_execute='/bin/bash', additional_volumes=None):
        """
        Do a "docker run" in interactive mode. This leaves the docker container running and waiting for commands. This
        method returns the Popen instance which can be used to send commands into the docker process.

        :type command_to_execute: str
        :type additional_volumes: dict[str, str]
        :return: The running "docker run -i" process
        :rtype: Popen
        """
        return self._execute_docker_run(command_to_execute, additional_volumes=additional_volumes, interactive=True)

    def _execute_docker_run(self, command_to_execute='', additional_volumes=None, interactive=False, remove=True):
        """
        Build a "docker run" command for this container and execute it in a subprocess.

        :type command_to_execute: str
        :type interactive: bool
        :type additional_volumes: dict[str, str]
        :rtype: Popen
        """
        docker_run_command = 'docker run'
        docker_arguments = [  # a list of tuples of the format (should_include_arg, arg_string)
            (self._host, ' -h "{}"'.format(self._host)),
            (self._user, ' -u "{}"'.format(self._user)),
            (interactive, ' -i'),
            (remove, ' --rm=true'),
        ]
        for should_include_arg, arg_string in docker_arguments:
            if should_include_arg:
                docker_run_command += arg_string

        volumes_to_mount = self._mounted_volumes.copy()
        volumes_to_mount.update(additional_volumes or {})
        for host_directory, container_directory in volumes_to_mount.items():
            docker_run_command += ' -v {}:{}'.format(host_directory, container_directory)

        docker_run_command += ' {} {}'.format(self._image, command_to_execute)
        return subprocess.Popen(docker_run_command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True, bufsize=0)

    def start_session(self):
        """
        Start an interactive session with this container. Be sure to call end_session() when done.
        """
        if self._active_session:
            self.end_session()
            raise RuntimeError('start_session() was called with an active session still running.')

        session_dir = TemporaryDirectory()  # a temp directory to hold exit codes and output for this session
        docker_process = self._run_interactive(
            additional_volumes={session_dir.name: session_dir.name}
        )
        self._active_session = _DockerSession(session_dir, docker_process)
        self._active_session.block_until_ready()

    def end_session(self):
        """
        End the interactive session for this container started by start_session().
        """
        if not self._active_session:
            raise RuntimeError('end_session() was called without a session to end.')

        self._active_session.end()
        self._active_session = None


class _DockerSession(object):
    def __init__(self, session_dir, docker_process):
        """
        :type session_dir: TemporaryDirectory
        :type docker_process: Popen
        """
        self._session_dir = session_dir
        self._docker_process = docker_process
        self._logger = log.get_logger(__name__)
        self._logger.debug('Started docker session, pid: {}', self._docker_process.pid)

    def execute(self, command):
        """
        Execute a command in the docker container. This can be called multiple times in a session. Returns the output
        and exit code of the command.

        :param command:
        :type command:
        :return:
        :rtype:
        """
        file_suffix = str(time.time())
        output_file_path = self._tempfile('output' + file_suffix)
        exit_code_file_path = self._tempfile('exit_code' + file_suffix)
        command = ('({}) > {} '      # run command in subshell and redirect output to output file
                   '2>&1\n'          # redirect stderr of subshell to stdout (same output file)
                   'echo $? > {}\n'  # save exit_code to exit code file
                   ).format(command, output_file_path, exit_code_file_path)

        # send the command to the docker container and wait for command to finish
        self._docker_process.stdin.write(command)
        self._docker_process.stdin.flush()

        exit_code = self._wait_for_exit(exit_code_file_path)
        with open(output_file_path, 'r') as output_file:
            output = output_file.read()

        return output, exit_code

    def end(self):
        """
        End the docker session, which exits the "docker run" process. This should always be called or else a docker
        container might be left running.
        """
        self._session_dir.cleanup()
        self._docker_process.communicate('exit\n')

    def block_until_ready(self):
        """
        Block until the container is ready. During development of this feature we noticed that starting multiple
        containers at the same time seemed to take a very long time, so this is here to allow us to start containers
        serially.
        """
        self.execute('echo "I am ready for your command."')

    def _wait_for_exit(self, exit_code_file):
        """
        Tail the specified exit code file until we can get a line from it. This signals that the command has finished.

        :param exit_code_file: The file path to watch for content to be added
        :type exit_code_file: str
        :return: The exit code that has been stored in exit_code_file
        :rtype: int
        """
        # tail the exit code file -- this allows us to block until the file contains an exit code
        tail_command = 'tail -n 1 -F {}'.format(exit_code_file)  # include "-n 1" in case the file already has a line
        tail_process = subprocess.Popen(tail_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        universal_newlines=True, bufsize=0)

        # block until we get a line from this file -- this will be the exit code of the executed docker command
        exit_code = tail_process.stdout.readline()  # blocks until a line is read

        # we've got our exit code, so kill the tail process and return
        tail_process.terminate()
        tail_process.wait()

        return int(exit_code)

    def _tempfile(self, name, overwrite_existing=True):
        """
        Create a file with the specified name in this session's session_dir. The default mode of 'w+' will
        truncate/overwrite the file if it already exists.

        :param name: The filename of the newly created file
        :type name: str
        :param overwrite_existing: Set this to False to avoid overwriting existing files with the same name
        :type overwrite_existing: bool
        :return: The full path to the newly created file in this session's session_dir
        :rtype: str
        """
        file_path = os.path.join(self._session_dir.name, name)
        mode = 'w+' if overwrite_existing else 'a+'
        open(file_path, mode).close()  # just create the file -- we just need it to exist, so don't leave it open.
        return file_path

    def __del__(self):
        """
        Make a (weak) attempt to close the session if client code forgets to. This shouldn't be relied upon since
        there are cases where Python will not call __del__.
        """
        try:
            self.end()
        except:  # pylint: disable=bare-except
            pass
