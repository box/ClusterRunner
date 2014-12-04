from unittest.mock import ANY, Mock, MagicMock, patch
import pexpect

from app.project_type.git import Git
from app.util.conf.configuration import Configuration
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestGit(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.project_type.git.fs.create_dir')
        self.patch('os.unlink')
        self.patch('os.symlink')
        self.mock_pexpect_child = self.patch('pexpect.spawn').return_value
        self.mock_pexpect_child.before = 'None'
        self.mock_pexpect_child.exitstatus = 0

    def test_timing_file_path_happy_path(self):
        git_env = Git("ssh://scm.dev.box.net/box/www/current", 'origin', 'refs/changes/78/151978/27')
        timing_file = git_env.timing_file_path('QUnit')
        self.assertEquals(
            Configuration['base_directory'] +
            '/timings/master/scm.dev.box.net/box/www/current/QUnit.timing.json',
            timing_file
        )

    def test_execute_command_in_project_specifies_cwd_if_exists(self):
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
            cwd='proj_dir',
            shell=ANY,
            stdout=ANY,
            stderr=ANY,
            start_new_session=ANY,
        )

    def test_execute_command_in_project_type_specifies_cwd_if_doesnt_exist(self):
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
            cwd=None,
            shell=ANY,
            stdout=ANY,
            stderr=ANY,
            start_new_session=ANY,
        )

    def test_execute_git_remote_command_auto_adds_known_host_if_prompted(self):
        prompted = False

        def expect_side_effect(*args, **kwargs):
            nonlocal prompted

            if args[0] == ['^User.*:', '^Pass.*:', '.*Are you sure you want to continue connecting.*'] \
                    and not prompted:
                prompted = True
                return 2
            elif args[0] == pexpect.EOF:
                return 0

            raise pexpect.TIMEOUT('some_msg')

        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        Configuration['git_strict_host_key_checking'] = False
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')
        git._execute_git_remote_command('some_command')
        self.mock_pexpect_child.sendline.assert_called_with("yes")

    def test_execute_git_remote_command_doesnt_auto_add_known_host_if_no_prompt(self):
        def expect_side_effect(*args, **kwargs):
            if args[0] == ['^User.*:', '^Pass.*:', '.*Are you sure you want to continue connecting.*']:
                raise pexpect.TIMEOUT('some_msg')
            if args[0] == pexpect.EOF:
                return 1
            return None
        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')

        git._execute_git_remote_command('some_command')

        self.assertEquals(self.mock_pexpect_child.sendline.call_count, 0)

    def test_execute_git_remote_command_raises_exception_if_strict_host_checking_and_prompted(self):
        def expect_side_effect(*args, **kwargs):
            if args[0] == ['^User.*:', '^Pass.*:', '.*Are you sure you want to continue connecting.*']:
                return 2
            return None

        self.mock_pexpect_child.expect.side_effect = expect_side_effect
        Configuration['git_strict_host_key_checking'] = True
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')
        self.assertRaises(RuntimeError, git._execute_git_remote_command, 'some_command')

    def test_get_full_repo_directory(self):
        Configuration['repo_directory'] = '/home/cr_user/.clusterrunner/repos/master'
        url = 'http://scm.example.com/path/to/project'

        repo_path = Git.get_full_repo_directory(url)

        self.assertEqual(repo_path, '/home/cr_user/.clusterrunner/repos/master/scm.example.com/path/to/project')

    def test_get_timing_file_directory(self):
        Configuration['timings_directory'] = '/home/cr_user/.clusterrunner/timing'
        url = 'http://scm.example.com/path/to/project'

        timings_path = Git.get_timing_file_directory(url)

        self.assertEqual(timings_path, '/home/cr_user/.clusterrunner/timing/scm.example.com/path/to/project')

    def test_get_repo_directory_removes_colon_from_directory_if_exists(self):
        Configuration['repo_directory'] = '/tmp/repos'
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')

        repo_directory = git.get_full_repo_directory('ssh://source_control.cr.com:1234/master')

        self.assertEqual(repo_directory, '/tmp/repos/source_control.cr.com1234/master')

    def test_get_timing_file_directory_removes_colon_from_directory_if_exists(self):
        Configuration['timings_directory'] = '/tmp/timings'
        git = Git("some_remote_value", 'origin', 'ref/to/some/branch')

        repo_directory = git.get_timing_file_directory('ssh://source_control.cr.com:1234/master')

        self.assertEqual(repo_directory, '/tmp/timings/source_control.cr.com1234/master')

    def test_setup_build_when_existing_repo_is_shallow_deletes_repo(self):
        url = 'url'
        repo_path = 'repo_path'
        git = Git(url)
        git._execute_and_raise_on_failure = Mock()
        git._repo_directory = repo_path
        git.execute_command_in_project = Mock(side_effect=[('', 0), ('', 0)])
        self.patch('os.path.exists').return_value = True
        self.patch('os.path.isfile').return_value = True
        mock_fs = self.patch('app.project_type.git.fs')
        mock_rmtree = self.patch('shutil.rmtree')
        git._execute_git_remote_command = Mock()
        mock_fs.create_dir.call_count = 0  # only measure calls made in _setup_build
        mock_rmtree.call_count = 0

        git._setup_build()

        self.assertEqual(mock_fs.create_dir.call_count, 1)
        self.assertEqual(mock_rmtree.call_count, 1)

