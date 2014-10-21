from app.project_type.git import Git
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestGit(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.project_type.git.create_dir')

    def test_timing_file_path_happy_path(self):
        self.patch('os.symlink')
        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        timing_file = git_env.timing_file_path('QUnit')
        self.assertEquals(
            Configuration['base_directory'] +
            '/timings/master/scm.dev.box.net/box/www/current/QUnit.timing.json',
            timing_file
        )

    def test_execute_command_in_project_specifies_cwd_if_exists(self):
        self.patch('os.symlink')
        os_path_exists_patch = self.patch('os.path.exists')
        os_path_exists_patch.return_value = True
        project_type_popen_patch = self.patch('app.project_type.project_type.Popen')
        project_type_popen_patch.return_value.communicate.return_value = None, None
        project_type_popen_patch.return_value.returncode = 0

        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        git_env.project_directory = 'proj_dir'
        git_env.execute_command_in_project('some_command')
        project_type_popen_patch.assert_called_once_with(
            'export PROJECT_DIR="proj_dir"; some_command',
            stderr=-2,
            cwd='proj_dir',
            shell=True,
            stdout=-1
        )

    def test_execute_command_in_project_type_specifies_cwd_if_doesnt_exist(self):
        self.patch('os.symlink')
        os_path_exists_patch = self.patch('os.path.exists')
        os_path_exists_patch.return_value = False
        project_type_popen_patch = self.patch('app.project_type.project_type.Popen')
        project_type_popen_patch.return_value.communicate.return_value = None, None
        project_type_popen_patch.return_value.returncode = 0

        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        git_env.project_directory = 'proj_dir'
        git_env.execute_command_in_project('some_command')
        project_type_popen_patch.assert_called_once_with(
            'export PROJECT_DIR="proj_dir"; some_command',
            stderr=-2,
            cwd=None,
            shell=True,
            stdout=-1
        )
