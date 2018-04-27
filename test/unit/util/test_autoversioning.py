from genty import genty, genty_dataset
import subprocess
from unittest.mock import MagicMock, call

from app.util import autoversioning
from test.framework.comparators import AnythingOfType
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestAutoversioning(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.unpatch('app.util.autoversioning.get_version')  # patched in BaseUnitTestCase for all other tests
        self.patch('app.util.autoversioning._MAJOR_MINOR_VERSION', new='1.0')
        self.check_output_mock = self.patch('app.util.autoversioning.subprocess.check_output')
        # Disable caching for every test case
        autoversioning.get_version.cache_clear()

    def test_get_version_returns_frozen_version_when_run_from_frozen_package(self):
        self.patch('app.util.autoversioning._get_frozen_package_version').return_value = '1.2.3'
        self.check_output_mock.side_effect = [subprocess.CalledProcessError(1, 'fake')]  # make all git commands fail

        actual_version = autoversioning.get_version()

        self.assertEqual(actual_version, '1.2.3', 'get_version() should return get_frozen_package_version()')

    def test_calculate_source_version_caches_computed_version(self):
        self._mock_git_commands_output()

        first_return_val = autoversioning.get_version()
        num_check_output_calls = self.check_output_mock.call_count
        second_return_val = autoversioning.get_version()

        self.assertEqual(first_return_val, second_return_val,
                         'get_version() should return the same version across multiple calls.')
        self.assertEqual(num_check_output_calls, self.check_output_mock.call_count,
                         'No calls to check_output() should occur after the first get_version() call.')

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
        status_side_effect = 'M app/util/autoversioning.py'.encode() if index_has_changed_files else b''
        current_head_commit = b'commit1\n' if commit_is_on_trunk else b'commit2\n'

        current_origin_manager_commit = b'commit3\n'
        all_commits = b'commit0\ncommit1\ncommit2\ncommit3\n'  # list of all 4 commit hashes in the repo
        check_output_side_effects_map = {
            ('rev-list', 'HEAD'): all_commits,
            ('rev-list', '--first-parent', 'commit1^..commit3'): b'commit1\ncommit3\n',  # commit2 is not a trunk commit
            ('rev-list', '--first-parent', 'commit2^..commit3'): b'commit1\n',
            ('status', '--porcelain'): status_side_effect,
            ('rev-parse', '--verify', 'HEAD'): current_head_commit,
            ('rev-parse', '--verify', 'origin/manager'): current_origin_manager_commit,
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
