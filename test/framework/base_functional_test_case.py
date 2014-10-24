from contextlib import suppress
import os
from os import path
import shutil
import tempfile
from unittest import TestCase

from app.util import log
from app.util.conf.base_config_loader import BASE_CONFIG_FILE_SECTION
from app.util.conf.config_file import ConfigFile
from app.util.secret import Secret
from test.framework.functional_test_cluster import FunctionalTestCluster, TestClusterTimeoutError


class BaseFunctionalTestCase(TestCase):
    """
    This is the base class for all functional tests. This class has two main purposes:
        - Make available a `FunctionalTestCluster` object for use in functional tests (self.cluster)
        - Implement any helper assertion methods that might be useful for making our tests easier to read and write
    """
    def setUp(self):
        # Configure logging to go to stdout. This makes debugging easier by allowing us to see logs for failed tests.
        log.configure_logging('DEBUG')

        Secret.set('testsecret')
        self.test_app_base_dir = tempfile.TemporaryDirectory()

        self.test_conf_file_path = self._create_test_config_file({
            'secret': Secret.get(),
            'base_directory': self.test_app_base_dir.name,
        })

        self.cluster = FunctionalTestCluster(
            conf_file_path=self.test_conf_file_path,
            verbose=self._get_test_verbosity(),
        )

    def _create_test_config_file(self, conf_values_to_set=None):
        """
        Create a temporary conf file just for this test.

        :return: The path to the conf file
        :rtype: str
        """
        # Copy default conf file to tmp location
        repo_dir = path.dirname(path.dirname(path.dirname(path.realpath(__file__))))
        self._conf_template_path = path.join(repo_dir, 'conf', 'default_clusterrunner.conf')
        test_conf_file_path = tempfile.NamedTemporaryFile().name
        shutil.copy(self._conf_template_path, test_conf_file_path)
        os.chmod(test_conf_file_path, ConfigFile.CONFIG_FILE_MODE)
        conf_file = ConfigFile(test_conf_file_path)

        # Set custom conf file values for this test
        conf_values_to_set = conf_values_to_set or {}
        for conf_key, conf_value in conf_values_to_set.items():
            conf_file.write_value(conf_key, conf_value, BASE_CONFIG_FILE_SECTION)

        return test_conf_file_path

    def tearDown(self):
        # Clean up files created during this test
        self.test_app_base_dir.cleanup()
        with suppress(FileNotFoundError):
            os.remove(self.test_conf_file_path)

        # Give the cluster a bit of extra time to finish working (before forcefully killing it and failing the test)
        with suppress(TestClusterTimeoutError):
            self.cluster.block_until_build_queue_empty(timeout=5)

        # Kill processes and make sure all processes exited with 0 exit code
        services = self.cluster.kill()
        for service in services:
            self.assertEqual(service.return_code, 0, 'Service running on url: {} should exit with code 0, but exited '
                                                     'with code {}.'.format(service.url, service.return_code))

    def _get_test_verbosity(self):
        """
        Get test verbosity from an env variable. We need to use an env var since Nose does not support specifying
        command-line test configuration natively. (But if we need more of these configuration paramaters, we should
        instead look at the 'nose-testconfig' plugin instead of adding tons of environment variables.)

        :return: Whether or not tests should be run verbosely
        :rtype: bool
        """
        is_verbose = os.getenv('CR_VERBOSE') not in ('0', '', None)  # default value of is_verbose is False
        return is_verbose

    def assert_build_status_contains_expected_data(self, build_id, expected_data):
        """
        Assert that the build status endpoint contains the expected fields and values. This assertion does an API
        request to the master service of self.cluster.

        :param build_id: The id of the build whose status to check
        :type build_id: int
        :param expected_data: A dict of expected keys and values in the build status response
        :type expected_data: dict
        """
        build_status = self.cluster.master_api_client.get_build_status(build_id).get('build')
        self.assertIsInstance(build_status, dict, 'Build status API request should return a dict.')
        self.assertDictContainsSubset(expected_data, build_status,
                                      'Build status API response should contain the expected status data.')

    def assert_build_has_successful_status(self, build_id):
        """
        Assert that the build status endpoint contains fields signifying the build was successful (had no failures).
        This assertion does an API request to the master service of self.cluster.

        :param build_id: The id of the build whose status to check
        :type build_id: int
        """
        expected_successful_build_params = {
            'result': 'NO_FAILURES',
            'status': 'FINISHED',
        }
        self.assert_build_status_contains_expected_data(build_id, expected_successful_build_params)

    def assert_build_has_failure_status(self, build_id):
        """
        Assert that the build status endpoint contains fields signifying the build was failed. This assertion does an
        API request to the master service of self.cluster.

        :param build_id: The id of the build whose status to check
        :type build_id: int
        """
        expected_failure_build_params = {
            'result': 'FAILURE',
            'status': 'FINISHED',
        }
        self.assert_build_status_contains_expected_data(build_id, expected_failure_build_params)

    def assert_atom_dir_file_contents_match_expected(self, build_id, subjob_id, atom_id, expected_atom_files_contents):
        """
        Assert that contents of files in the artifact directory for the specified atom match the expected contents.

        :param build_id: The id of the build whose files to check
        :type build_id: int
        :param subjob_id: The id of the subjob whose files to check
        :type subjob_id: int
        :param atom_id: The id of the atom whose files to check
        :type atom_id: int
        :param expected_atom_files_contents: A mapping of filename to expected file contents string; the file with the
            specified name is expected to be in the atom artifact directory for the specified atom.
        :type expected_atom_files_contents: dict[str, str]
        """
        # Note that we construct the artifact file path manually instead of getting it from the config classes.
        # This is intentional because the config classes are part of the system under test.
        atom_artifact_dir_relpath = os.path.join('results', 'master', str(build_id),
                                                 'artifact_{}_{}'.format(subjob_id, atom_id))
        atom_artifact_dir_abspath = os.path.join(self.test_app_base_dir.name, atom_artifact_dir_relpath)
        atom_artifact_dir_contents = os.listdir(atom_artifact_dir_abspath)

        for filename, expected_file_contents in expected_atom_files_contents.items():
            expected_atom_file_path = os.path.join(atom_artifact_dir_abspath, filename)
            self.assertTrue(
                os.path.isfile(expected_atom_file_path),
                'A file named "{}" is expected to exist in the results directory at "{}". Actual contents of this '
                'directory are: {}.'.format(filename, atom_artifact_dir_relpath, atom_artifact_dir_contents))
            with open(expected_atom_file_path) as f:
                actual_file_contents = f.read()
            self.assertEqual(actual_file_contents, expected_file_contents,
                             'The contents of the file named "{}" in the artifact directory "{}" should match the '
                             'expected contents.'.format(filename, atom_artifact_dir_relpath))

    def assert_build_artifact_contents_match_expected(self, build_id, expected_build_artifact_contents):
        """
        Assert that artifact files for this build have the expected contents.

        :param build_id: The id of the build whose artifacts to check
        :type build_id: int
        :param expected_build_artifact_contents: A list of lists of mappings from artifact filename to artifact contents
            string; the outer list corresponds to subjob ids, the inner list corresponds to atom ids, and the dict
            should be a mapping of filenames to expected file contents for the corresponding atom. See the configs in
            functional_test_job_configs.py for examples.
        :type expected_build_artifact_contents: list[list[dict[str, str]]]
        """
        for subjob_id, expected_subjob_files_contents in enumerate(expected_build_artifact_contents):
            for atom_id, expected_atom_files_contents in enumerate(expected_subjob_files_contents):
                self.assert_atom_dir_file_contents_match_expected(build_id, subjob_id, atom_id,
                                                                  expected_atom_files_contents)
