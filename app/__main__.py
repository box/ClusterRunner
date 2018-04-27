#!/usr/bin/env python

import argparse
import os
import random
import string
import sys
import threading
import time

from app.subcommands.build_subcommand import BuildSubcommand
from app.subcommands.deploy_subcommand import DeploySubcommand
from app.subcommands.manager_subcommand import ManagerSubcommand
from app.subcommands.shutdown_subcommand import ShutdownSubcommand
from app.subcommands.worker_subcommand import WorkerSubcommand
from app.subcommands.stop_subcommand import StopSubcommand
from app.util import app_info, autoversioning, log, util
from app.util.argument_parsing import ClusterRunnerArgumentParser, ClusterRunnerHelpFormatter
from app.util.conf.base_config_loader import BASE_CONFIG_FILE_SECTION, BaseConfigLoader
from app.util.conf.config_file import ConfigFile
from app.util.conf.configuration import Configuration
from app.util.conf.deploy_config_loader import DeployConfigLoader
from app.util.conf.manager_config_loader import ManagerConfigLoader
from app.util.conf.worker_config_loader import WorkerConfigLoader
from app.util.conf.stop_config_loader import StopConfigLoader
from app.util.secret import Secret
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


def _parse_args(args):
    parser = ClusterRunnerArgumentParser()
    parser.add_argument(
        '-V', '--version',
        action='version', version='ClusterRunner ' + autoversioning.get_version())

    subparsers = parser.add_subparsers(
        title='Commands',
        description='See "{} <command> --help" for more info on a specific command.'.format(sys.argv[0]),
        dest='subcommand',
    )
    subparsers.required = True

    # arguments specific to manager
    manager_parser = subparsers.add_parser(
        'manager',
        help='Run a ClusterRunner manager service.', formatter_class=ClusterRunnerHelpFormatter)
    manager_parser.add_argument(
        '-p', '--port',
        type=int,
        help='the port on which to run the manager service. '
             'This will be read from conf if unspecified, and defaults to 43000')
    manager_parser.set_defaults(subcommand_class=ManagerSubcommand)

    # arguments specific to worker
    worker_parser = subparsers.add_parser(
        'worker',
        help='Run a ClusterRunner worker service.', formatter_class=ClusterRunnerHelpFormatter)
    worker_parser.add_argument(
        '-p', '--port',
        type=int,
        help='the port on which to run the worker service. '
             'This will be read from conf if unspecified, and defaults to 43001')
    worker_parser.add_argument(
        '-m', '--manager-url',
        help='the url of the manager service with which the worker should communicate')
    worker_parser.add_argument(
        '-e', '--num-executors',
        type=int, help='the number of executors to use, defaults to 1')
    worker_parser.set_defaults(subcommand_class=WorkerSubcommand)

    # arguments specific to both manager and worker
    for subparser in (manager_parser, worker_parser):
        subparser.add_argument(
            '--eventlog-file',
            help='change the file that eventlogs are written to, or "STDOUT" to log to stdout')

    # arguments specific to the 'stop' subcommand
    stop_parser = subparsers.add_parser(
        'stop',
        help='Stop all ClusterRunner services running on this host.', formatter_class=ClusterRunnerHelpFormatter)
    stop_parser.set_defaults(subcommand_class=StopSubcommand)

    # arguments specific to the 'deploy' subcommand
    deploy_parser = subparsers.add_parser(
        'deploy', help='Deploy clusterrunner to manager and workers.', formatter_class=ClusterRunnerHelpFormatter)
    deploy_parser.add_argument(
        '-m', '--manager', type=str,
        help=('The manager host url (no port) to deploy the manager on. This will be read from conf '
              'if unspecified, and defaults to localhost.'))
    deploy_parser.add_argument(
        '--manager-port', type=int,
        help=('The port on which the manager service will run. '
              'This will be read from conf if unspecified, and defaults to 43000.'))
    deploy_parser.add_argument(
        '-s', '--workers', type=str, nargs='+',
        help='The space separated list of host urls (without ports) to be deployed as workers.')
    deploy_parser.add_argument(
        '--worker-port', type=int,
        help=('The port on which all of the worker services will run. '
              'This will be read from conf if unspecified, and defaults to 43001.'))
    deploy_parser.add_argument(
        '-n', '--num-executors', type=int, help='The number of executors to use per worker, defaults to 30.')
    deploy_parser.set_defaults(subcommand_class=DeploySubcommand)

    # arguments specific to execute-build mode
    build_parser = subparsers.add_parser(
        'build',
        help='Execute a build and wait for it to complete.', formatter_class=ClusterRunnerHelpFormatter)

    build_parser.add_argument(
        '--manager-url',
        help='the url of the ClusterRunner manager that will execute this build.')
    build_parser.add_argument(
        '-j', '--job-name',
        help='the name of the job to run')
    build_parser.add_argument(
        '-f', '--remote-file',
        default=None,
        help='remote file to use in the project with the format of: <NAME> <URL>',
        action='append',
        nargs=2)

    _add_project_type_subparsers(build_parser)
    build_parser.set_defaults(subcommand_class=BuildSubcommand)

    shutdown_parser = subparsers.add_parser(
        'shutdown',
        help=('Put workers in shutdown mode so they can be terminated safely. Workers in shutdown '
              'mode will finish any subjobs they are currently executing, then die.'),
        formatter_class=ClusterRunnerHelpFormatter
    )
    shutdown_parser.add_argument(
        '-m', '--manager-url',
        help='The url of the manager, including the port'
    )
    shutdown_parser.add_argument(
        '-a', '--all-workers',
        action='store_true',
        help='Shutdown all workers'
    )
    shutdown_parser.add_argument(
        '-s', '--worker-id',
        action='append',
        dest='worker_ids',
        help='A worker id to shut down.'
    )

    shutdown_parser.set_defaults(subcommand_class=ShutdownSubcommand)

    for subparser in (manager_parser, worker_parser, build_parser, stop_parser, deploy_parser, shutdown_parser):
        subparser.add_argument(
            '-v', '--verbose',
            action='store_const', const='DEBUG', dest='log_level', help='set the log level to "debug"')
        subparser.add_argument(
            '-q', '--quiet',
            action='store_const', const='ERROR', dest='log_level', help='set the log level to "error"')
        subparser.add_argument(
            '-c', '--config-file',
            help='The location of the clusterrunner config file, defaults to ~/.clusterrunner/clusterrunner.conf'
        )

    parsed_args = vars(parser.parse_args(args))  # vars() converts the namespace to a dict
    return parsed_args


def _add_project_type_subparsers(build_parser):
    """
    Iterate through each project type (e.g., git, etc.) and add a separate parser with the appropriate
    arguments.

    :type build_parser: ArgumentParser
    """
    project_type_subparsers = build_parser.add_subparsers(
        title='Project types',
        description='Specify the project type of the build request to be sent. '
                    'See "<type> --help" for documentation on type-specific arguments.',
        dest='build_type',
    )
    # for every project type class, add a parser with arguments matching each project type's class constructor args
    project_types = util.project_type_subclasses_by_name()
    help_argument_blacklist = ['remote_files', 'build_project_directory']
    for project_type_name, project_type_class in project_types.items():
        project_type_parser = project_type_subparsers.add_parser(
            project_type_name,
            help='Execute a {} type build'.format(project_type_name.title()),
            formatter_class=ClusterRunnerHelpFormatter,
        )

        env_args_info = project_type_class.constructor_arguments_info(blacklist=help_argument_blacklist)
        for arg_name, arg_info in env_args_info.items():
            fixed_arg_name = arg_name.replace('_', '-')
            if isinstance(arg_info.default, bool):
                project_type_parser.add_argument(
                    '--' + fixed_arg_name,
                    dest=arg_name,
                    action='store_true',
                    help=arg_info.help,
                    default=argparse.SUPPRESS
                )
                project_type_parser.add_argument(
                    '--no-' + fixed_arg_name,
                    dest=arg_name,
                    action='store_false',
                    help=arg_info.help,
                    default=argparse.SUPPRESS
                )
                project_type_parser.set_defaults(arg_name=arg_info.default)
            else:
                project_type_parser.add_argument(
                    '--' + fixed_arg_name,  # example: constructor arg "job_name" --> cmd line arg "--job-name"
                    help=arg_info.help,
                    required=arg_info.required,
                    default=argparse.SUPPRESS,  # don't add argument to parsed_args unless a value was explicitly specified
                )


def _initialize_configuration(app_subcommand, config_filename):
    """
    Load the default conf values (including subcommand-specific values), then find the conf file and read overrides.

    :param app_subcommand: The application subcommand (e.g., manager, worker, build)
    :type app_subcommand: str
    :type config_filename: str
    """
    app_subcommand_conf_loaders = {
        'manager': ManagerConfigLoader(),
        'worker': WorkerConfigLoader(),
        'build': ManagerConfigLoader(),
        'deploy': DeployConfigLoader(),
        'stop': StopConfigLoader(),
    }
    conf_loader = app_subcommand_conf_loaders.get(app_subcommand) or BaseConfigLoader()
    config = Configuration.singleton()

    # First, set the defaults, then load any config from disk, then set additional config values based on the
    # base_directory
    conf_loader.configure_defaults(config)
    config_filename = config_filename or Configuration['config_file']
    conf_loader.load_from_config_file(config, config_filename)
    conf_loader.configure_postload(config)

    _set_secret(config_filename)


def _set_secret(config_filename):
    if 'secret' in Configuration and Configuration['secret'] is not None:
        secret = Configuration['secret']
    else:  # No secret found, generate one and persist it
        secret_length = 128
        chars = string.ascii_lowercase + string.digits
        secret = ''.join(random.SystemRandom().choice(chars) for _ in range(secret_length))
        conf_file = ConfigFile(config_filename)
        conf_file.write_value('secret', secret, BASE_CONFIG_FILE_SECTION)
    Secret.set(secret)


def _start_app_force_kill_countdown(seconds):
    """
    Start a daemon thread that will wait the specified number of seconds and then dump debug info and forcefully kill
    the app. Note that this hard kill will only be executed if the app is unexpectedly hanging. Under normal
    circumstances, the app will exit cleanly (all nondaemon threads will finish) before the specified delay has elapsed.

    :param seconds: The number of seconds to wait before dumping debug info and hard killing the app
    :type seconds: int
    """
    def log_app_debug_info_and_force_kill_after_delay():
        time.sleep(seconds)
        logger = log.get_logger(__name__)
        logger.error('ClusterRunner did not exit within {} seconds. App debug info:\n\n{}.',
                     seconds, app_info.get_app_info_string())
        logger.critical('ClusterRunner seems to be hanging unexpectedly. Hard killing the process. Farewell!')
        os._exit(1)  # pylint: disable=protected-access

    # Execute on a daemon thread so that the countdown itself will not prevent the app from exiting naturally.
    threading.Thread(target=log_app_debug_info_and_force_kill_after_delay, name='SuicideThread', daemon=True).start()


def main(args=None):
    """
    This is the single entry point of the ClusterRunner application. This function feeds the command line parameters as
    keyword args directly into the run() method of the appropriate Subcommand subclass.

    Note that for the manager and worker subcommands, we execute all major application logic (including the web server)
    on a separate thread (not the main thread). This frees up the main thread to be responsible for facilitating
    graceful application shutdown by intercepting external signals and executing teardown handlers.
    """
    parsed_args = _parse_args(args)
    _initialize_configuration(parsed_args.pop('subcommand'), parsed_args.pop('config_file'))
    subcommand_class = parsed_args.pop('subcommand_class')  # defined in _parse_args() by subparser.set_defaults()

    try:
        unhandled_exception_handler = UnhandledExceptionHandler.singleton()
        with unhandled_exception_handler:
            subcommand_class().run(**parsed_args)

    finally:
        # The force kill countdown is not an UnhandledExceptionHandler teardown callback because we want it to execute
        # in all situations (not only when there is an unhandled exception).
        _start_app_force_kill_countdown(seconds=10)


if __name__ == '__main__':
    main()
