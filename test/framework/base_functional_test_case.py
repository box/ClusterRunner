import json
import os
import requests
from unittest import TestCase

from app.client.service_runner import ServiceRunner
from main import _set_secret
from app.util.secret import Secret
from app.util.conf.slave_config_loader import SlaveConfigLoader
from app.util.conf.configuration import Configuration
from app.util.url_builder import UrlBuilder


class BaseFunctionalTestCase(TestCase):
    _master_url = 'localhost:43000'
    _default_cluster_config = {
        'num_slaves': 5,
        'num_executors_per_slave': 5,
    }

    def setUp(self):
        SlaveConfigLoader().configure_defaults(Configuration.singleton())
        cluster_config = self._get_cluster_config_for_current_test()

        self.service_runner = ServiceRunner(self._master_url, './main.py')
        self.service_runner.run_master()
        for n in range(int(cluster_config['num_slaves'])):
            base_slave_port = Configuration['port']
            self.service_runner.run_slave(base_slave_port + n)
        _set_secret(Configuration['config_file'])

    def tearDown(self):
        self.service_runner.block_until_build_queue_empty()
        self.service_runner.kill()

    def post_new_build_request(self, job_params, project_type='directory', directory='/tmp'):
        """
        :param job_params:
        :type job_params: dict
        :return: requests.Response
        """
        num_subjobs = job_params['num_subjobs']
        config_yaml = (
            'MockJob:\n'
            '    max_executors: 50\n'
            '    commands:\n'
            '        - echo $MOCKVALUE >> $ARTIFACT_DIR/result.txt\n'
            '    atomizers:\n'
            '        - printf \'export MOCKVALUE=hello%d\\n\' {1..' + str(num_subjobs) + '}\n'
        )
        master_api = UrlBuilder(self._master_url)
        build_url = master_api.url('build')
        data = {
            "type": project_type,
            "project_directory": directory,
            "config": config_yaml,
            }
        message = json.dumps(data)
        return requests.post(build_url, data=message, headers=Secret.header(message, Secret.get())).json()

    def assert_result_paths_exist(self, result_paths):
        """
        Wait for any queued build to finish, then assert the results are in place
        :param result_paths: The files and directories to search for
        :type result_paths: list [str]
        """
        self.service_runner.block_until_build_queue_empty()
        for path in result_paths:
            full_path = os.path.join(
                os.path.expanduser('~/'),
                '.clusterrunner',
                'results',
                'master',
                path
            )
            self.assertTrue(os.path.exists(full_path), 'Path {} does not exist.'.format(full_path))

    def _get_cluster_config_for_current_test(self):
        cluster_config = dict(self._default_cluster_config)
        test_method = getattr(type(self), self._testMethodName)
        test_specific_config = getattr(test_method, 'cluster_config', {})
        cluster_config.update(test_specific_config)
        return cluster_config

    def _get_test_verbosity(self):
        """
        Get test verbosity from an environment variable. We need to do this since Nose does not support specifying
        command-line test config values out of the box. (But if we need more of these configuration paramaters, we
        should instead look at the 'nose-testconfig' plugin instead of adding tons of environment variables.)
        :rtype: bool
        """
        is_verbose = os.getenv('CR_VERBOSE') not in ('0', '', None)  # default: is_verbose=False
        return is_verbose
