import os
import subprocess
import sys

from app.util import fs


_MAJOR_MINOR_VERSION = '0.5'

_calculated_version = None  # We will cache the calculated version so that it can't change during execution.
_VERSION_FILE_PATH = os.path.join(os.path.dirname(__file__), 'package_version.py')
_VERSION_FILE_BACKUP_PATH = os.path.join(os.path.dirname(__file__), 'package_version.py.bak')


def get_version():
    """
    Get the version of the application. This method should return the correct version in both the frozen and unfrozen
    (running from cloned source) cases.

    :return: The version of the application
    :rtype: str
    """
    if getattr(sys, 'frozen', False):
        return _get_frozen_package_version()  # frozen/packaged

    return _calculate_source_version()  # unfrozen/running from source


def _try_rename(src, dst):
    try:
        os.rename(src, dst)
    except FileExistsError:
        # Skip backing up the original package_version.py if a FileExistsError happened.
        # This might happen on Windows as NTFS doesn't support writing to a file while the file is opened in python.
        pass


def write_package_version_file(package_version_string):
    """
    Write the specfied version string to package_version.py. This method is intended to be called during the process of
    freezing a package for release. This in-effect hard codes the version into the frozen package.

    This also backs up the original file, which can be restored with another method in this module.

    :param package_version_string: The version to write to the file -- presumably the output of get_version()
    :type package_version_string: str
    """
    package_version_file_contents = 'version = "{}"  # DO NOT COMMIT\n'.format(package_version_string)

    _try_rename(_VERSION_FILE_PATH, _VERSION_FILE_BACKUP_PATH)  # Backup the original file.
    fs.write_file(package_version_file_contents, _VERSION_FILE_PATH)


def restore_original_package_version_file():
    """
    Restore the backed up version of package_version.py. This is just a convenience method to help us remember not to
    commit changes to the package version file.
    """
    _try_rename(_VERSION_FILE_BACKUP_PATH, _VERSION_FILE_PATH)


def _get_frozen_package_version():
    """
    Return the hard coded version from package_version.py. The package_version module is only populated with the actual
    version during the freeze process, so this method only returns the correct version if run from a frozen package.

    :return: The version of the (frozen) application
    :rtype: str
    """

    # only import package_version when needed as on Windows once imported, the actual package_version.py can't be
    # edited anymore
    from app.util import package_version
    return package_version.version


def _calculate_source_version():
    """
    Calculate the version using a scheme based off of git repo info. Note that since this depends on the git history,
    this will *not* work from a frozen package (which does not include the git repo data). This will only work in the
    context of running the application from the cloned git repo.

    If one of the git commands used to calculate the version fails unexpectedly, the patch in the version string will
    be set to "???".

    :return: The version of the (source) application
    :rtype: str
    """
    global _calculated_version

    if _calculated_version is None:
        try:
            head_commit_hash = _get_commit_hash_from_revision_param('HEAD')
            head_commit_is_on_trunk = _is_commit_hash_in_masters_first_parent_chain(head_commit_hash)

            commit_count = _get_repo_commit_count()
            hash_extension = '' if head_commit_is_on_trunk else '-{}'.format(head_commit_hash[:7])
            mod_extension = '' if not _repo_has_uncommited_changes() else '-mod'
            _calculated_version = '{}.{}{}{}'.format(_MAJOR_MINOR_VERSION, commit_count, hash_extension, mod_extension)

        except subprocess.CalledProcessError:
            _calculated_version = '{}.???'.format(_MAJOR_MINOR_VERSION)

    return _calculated_version


def _get_repo_commit_count():
    """
    :return: The number of commits in the repo
    :rtype: int
    """
    commit_list = _execute_local_git_command('rev-list', 'HEAD').split()
    return len(commit_list)


def _repo_has_uncommited_changes():
    """
    Check if the git repo has any changes to tracked files that haven't been committed.

    :return: Whether or not the repo has uncommited changes to tracked files
    :rtype: bool
    """
    has_uncommited_changes = False
    try:
        _execute_local_git_command('diff-index', '--quiet', 'HEAD')
    except subprocess.CalledProcessError:  # CalledProcessError is raised if command exits with non-zero exit code
        has_uncommited_changes = True

    return has_uncommited_changes


def _is_commit_hash_in_masters_first_parent_chain(commit_hash):
    """
    Check if the current HEAD is in the first-parent chain of origin/master. The first-parent chain of origin/master
    consists of all the "trunk" commits. All other commits are either on merged branches or haven't been merged at all.

    :type commit_hash: str
    :rtype: bool
    """
    master_commit_hash = _get_commit_hash_from_revision_param('origin/master')
    first_parent_chain = _execute_local_git_command(
        'rev-list',
        '--first-parent',
        '{}^..{}'.format(commit_hash, master_commit_hash)).split()
    return commit_hash in first_parent_chain


def _get_commit_hash_from_revision_param(revision_param):
    """
    Get the full git commit hash from a given revision parameter (branch name, short hash, etc.)

    :type revision_param: str
    :rtype: str
    """
    return _execute_local_git_command('rev-parse', '--verify', revision_param).strip()


def _execute_local_git_command(*args):
    """
    Execute a git command in the ClusterRunner git repo that we are currently executing from. subprocess.check_output()
    raises a CalledProcessError exception if the command exits with a nonzero exit code.

    :param args: The command arguments to provide to git
    :type args: tuple
    :return: The output of the git command
    :rtype: str
    """
    command_output = subprocess.check_output(
        ['git'] + list(args),
        cwd=os.path.dirname(__file__),
    )
    return command_output.decode()
