from genty import genty, genty_dataset
import subprocess
from unittest.mock import MagicMock, call

from app.util import autoversioning, package_version
from test.framework.comparators import AnythingOfType
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestAutoversioning(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.unpatch('app.util.autoversioning.get_version')  # patched in BaseUnitTestCase for all other tests
        self.patch('app.util.autoversioning._MAJOR_MINOR_VERSION', new='1.0')
        self.check_output_mock = self.patch('app.util.autoversioning.subprocess.check_output')
        autoversioning._calculated_version = None  # reset cached version between individual tests

    def test_get_version_returns_frozen_version_when_run_from_frozen_package(self):
        self.patch('app.util.autoversioning.sys').frozen = True
        package_version.version = '1.2.3'  # package_version is written during freeze, so this is the "frozen" version.

        actual_version = autoversioning.get_version()

        self.assertFalse(self.check_output_mock.called, 'No subprocess call should be necessary to get frozen version.')
        self.assertEqual(actual_version, '1.2.3', 'get_version() should return what is written in package_version.py.')

    def test_write_package_version_file_writes_a_valid_python_file(self):
        def fake_write_file(file_contents, _):
            vars_set_in_file = {}
            exec(file_contents, {}, vars_set_in_file)  # this will raise if file_contents is not valid python code
            self.assertEqual(vars_set_in_file.get('version'), '1.2.3', 'The file written should be Python code that '
                                                                       'sets a "version" variable.')
        self.patch('app.util.autoversioning.os')
        self.patch('app.util.autoversioning.fs').write_file.side_effect = fake_write_file

        autoversioning.write_package_version_file(package_version_string='1.2.3')

    def test_write_package_version_file_backs_up_original_file_before_writing(self):
        parent_mock = MagicMock()  # create a parent mock so we can assert on the order of child mock calls.
        parent_mock.attach_mock(self.patch('app.util.autoversioning.os'), 'os')
        parent_mock.attach_mock(self.patch('app.util.autoversioning.fs'), 'fs')

        autoversioning.write_package_version_file(package_version_string='1.2.3')

        expected_rename_call = call.os.rename(AnythingOfType(str), AnythingOfType(str))
        expected_write_file_call = call.fs.write_file(AnythingOfType(str), AnythingOfType(str))
        self.assertLess(parent_mock.method_calls.index(expected_rename_call),
                        parent_mock.method_calls.index(expected_write_file_call),
                        'write_package_version_file() should rename the original file before writing the new file.')

    def test_restore_original_package_version_file_restores_correctly(self):
        def fake_os_rename(source_file_path, target_file_path):
            # Store the args the first time rename is called so we can use these values in later asserts.
            nonlocal original_pkg_ver_path, backup_pkg_ver_path
            if None in (original_pkg_ver_path, backup_pkg_ver_path):
                original_pkg_ver_path = source_file_path
                backup_pkg_ver_path = target_file_path

        original_pkg_ver_path = None
        backup_pkg_ver_path = None
        self.patch('app.util.autoversioning.fs')
        mock_os = self.patch('app.util.autoversioning.os')
        mock_os.rename.side_effect = fake_os_rename

        autoversioning.write_package_version_file(package_version_string='1.2.3')
        autoversioning.restore_original_package_version_file()

        backup_os_rename_call = call.rename(original_pkg_ver_path, backup_pkg_ver_path)
        restore_os_rename_call = call.rename(backup_pkg_ver_path, original_pkg_ver_path)
        self.assertLess(mock_os.method_calls.index(backup_os_rename_call),
                        mock_os.method_calls.index(restore_os_rename_call),
                        'restore_original_package_version_file() should restore whatever file was backed up in the '
                        'previous call to write_package_version_file().')

    def test_calculate_source_version_caches_computed_version(self):
        self._mock_git_commands_output()

        first_return_val = autoversioning.get_version()
        num_check_output_calls = self.check_output_mock.call_count
        second_return_val = autoversioning.get_version()

        self.assertEqual(first_return_val, second_return_val,
                         'get_version() should return the same version across multiple calls.')
        self.assertEqual(num_check_output_calls, self.check_output_mock.call_count,
                         'No calls to check_output() should occur after the first get_version() call.')

    def test_unexpected_failure_in_git_command_sets_patch_version_to_unknown(self):
        self.check_output_mock.side_effect = [subprocess.CalledProcessError(1, 'fake')]  # make all git commands fail

        actual_version = autoversioning.get_version()

        self.assertEqual(actual_version, '1.0.???', 'get_version() should not raise exception if git commands fail, '
                                                    'and should just set the patch version to "???".')

    @genty_dataset(
        head_commit_is_on_trunk=(True, False, '1.0.4'),
        head_commit_is_on_branch=(False, False, '1.0.4-commit2'),
        head_commit_is_on_trunk_with_changed_files=(True, True, '1.0.4-mod'),
        head_commit_is_on_branch_with_changed_files=(False, True, '1.0.4-commit2-mod'),
    )
    def test_calculated_source_version_is_correct_when(self, commit_is_on_trunk, has_changed_files, expected_version):
        self._mock_git_commands_output(commit_is_on_trunk, has_changed_files)

        actual_version = autoversioning.get_version()

        self.assertEqual(actual_version, expected_version)

    def _mock_git_commands_output(self, commit_is_on_trunk=True, index_has_changed_files=False):
        diff_index_side_effect = subprocess.CalledProcessError(1, 'fake') if index_has_changed_files else b'\n'
        current_head_commit = b'commit1\n' if commit_is_on_trunk else b'commit2\n'

        current_origin_master_commit = b'commit3\n'
        all_commits = b'commit0\ncommit1\ncommit2\ncommit3\n'  # list of all 4 commit hashes in the repo
        check_output_side_effects_map = {
            ('rev-list', 'HEAD'): all_commits,
            ('rev-list', '--first-parent', 'commit1^..commit3'): b'commit1\ncommit3\n',  # commit2 is not a trunk commit
            ('rev-list', '--first-parent', 'commit2^..commit3'): b'commit1\n',
            ('diff-index', '--quiet', 'HEAD'): diff_index_side_effect,
            ('rev-parse', '--verify', 'HEAD'): current_head_commit,
            ('rev-parse', '--verify', 'origin/master'): current_origin_master_commit,
        }

        def fake_check_output(cmd_args, *args, **kwargs):
            self.assertEqual(cmd_args[0], 'git', 'All commands during autoversioning are expected to be git commands.')
            return_value = check_output_side_effects_map.get(tuple(cmd_args[1:]))
            self.assertIsNotNone(return_value, 'Call to check_output with arguments {} should have a mock side effect '
                                               'defined for this test.'.format(cmd_args))
            if isinstance(return_value, Exception):
                raise return_value
            return return_value

        self.check_output_mock.side_effect = fake_check_output
