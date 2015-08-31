import os
from os.path import basename, dirname, relpath

from test.framework.base_unit_test_case import BaseUnitTestCase


class TestTest(BaseUnitTestCase):
    """
    This test class is a place for "meta-tests" that attempt to ensure that our tests are being run correctly.
    """
    def test_all_test_subdirectories_have_init_py_file(self):
        # If a directory is missing an __init__.py, then tests in that directory will not be run!
        repo_test_dir_path = dirname(dirname(__file__))
        self.assertEqual(basename(repo_test_dir_path), 'test', 'repo_test_dir_path should be the path of the top-level '
                                                               '"test" directory in the ClusterRunner repo.')

        exempt_dirs = ['__pycache__', '.hypothesis']  # skip special directories
        for dir_path, _, files in os.walk(repo_test_dir_path):
            if any(exempt_dir in dir_path for exempt_dir in exempt_dirs):
                continue

            self.assertIn(
                '__init__.py', files,
                'The test directory "{}" does not appear to have an __init__.py file. This will prevent tests in that '
                'directory from running via "nosetests /test".'.format(relpath(dir_path, repo_test_dir_path)))
