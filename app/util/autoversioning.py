import functools
import os
import subprocess
from subprocess import CalledProcessError

_MAJOR_MINOR_VERSION = '0.5'


@functools.lru_cache(maxsize=1)
def get_version():
    """
    Get the version of the application. This method should return the correct version in both the
    packaged and local (running inside the git repo) cases. A valid version string must be returned
    to prevent execution and/or build errors. Version detection will fail in shallow-cloned repo.

    :return: The version of the application
    :rtype: str
    """
    return _calculate_source_version() or _get_frozen_package_version() or '0.0.0'


def _get_frozen_package_version():
    """
    :return: the installed version from pkg_resources.
    :rtype: str
    """
    try:
        import pkg_resources
        return pkg_resources.get_distribution('clusterrunner').version  # pylint: disable=no-member
    except Exception:  # pylint: disable=broad-except
        return None


def _calculate_source_version():
    """
    Calculate the version using a scheme based off of git repo info. Note that since this depends on
    the git history, this will *not* work from a distribution package (which does not include the
    git repo data). This will only work in the context of running the application from the cloned
    git repo.

    If this is running outside of a git repo, it will handle the CalledProcessError exception and
    return None.

    :return: The version of the (source) application
    :rtype: str
    """
    try:
        head_commit_hash = _get_commit_hash_from_revision_param('HEAD')
        head_commit_is_on_trunk = _is_commit_hash_in_masters_first_parent_chain(head_commit_hash)

        commit_count = _get_repo_commit_count()
        hash_extension = '' if head_commit_is_on_trunk else '-{}'.format(head_commit_hash[:7])
        mod_extension = '' if not _repo_has_uncommited_changes() else '-mod'
        return '{}.{}{}{}'.format(_MAJOR_MINOR_VERSION, commit_count, hash_extension, mod_extension)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


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
    # Any output from "status" indicates changes.
    return bool(_execute_local_git_command('status', '--porcelain'))


def _is_commit_hash_in_masters_first_parent_chain(commit_hash):
    """
    Check if the current HEAD is in the first-parent chain of origin/master. The first-parent chain
    of origin/master consists of all the "trunk" commits. All other commits are either on merged
    branches or haven't been merged at all.

    :type commit_hash: str
    :rtype: bool
    :raises CalledProcessError: if there is no local git repo or is a shallow clone
    :raises FileNotFoundError: if git command is not available.
    """
    _fetch_remote_branch_from_refspec('origin', 'master')
    master_commit_hash = _get_commit_hash_from_revision_param('origin/master')
    first_parent_chain = _execute_local_git_command(
        'rev-list',
        '--first-parent',
        '{}^..{}'.format(commit_hash, master_commit_hash)).split()
    return commit_hash in first_parent_chain


def _fetch_remote_branch_from_refspec(remote: str, branch: str) -> None:
    """
    Fetch/update the remote ref from a given remote and branch name. This is used when the working
    repo does not have the local origin/master ref (e.g. during a Jenkins PR build).

    :raises FileNotFoundError: if git command is not available.
    """
    try:
        _execute_local_git_command('fetch', remote,
                                   "refs/heads/{1}:refs/remotes/{0}/{1}".format(remote, branch))
    except CalledProcessError:
        # "git fetch" may fail during the docker build so it must be ignored.
        pass


def _get_commit_hash_from_revision_param(revision_param):
    """
    Get the full git commit hash from a given revision parameter (branch name, short hash, etc.)

    :type revision_param: str
    :rtype: str
    :raises FileNotFoundError: if git command is not available.
    """
    return _execute_local_git_command('rev-parse', '--verify', revision_param).strip()


def _execute_local_git_command(*args):
    """
    Execute a git command in the ClusterRunner git repo that we are currently executing from.
    subprocess.check_output() raises a CalledProcessError exception if the command exits with a
    nonzero exit code.

    :param args: The command arguments to provide to git
    :type args: tuple
    :return: The output of the git command
    :rtype: str
    :raises FileNotFoundError: if git command is not available.
    :raises CalledProcessError: if command exists non-zero.
    """
    command_output = subprocess.check_output(
        ['git'] + list(args),
        cwd=os.path.dirname(__file__),
        stderr=subprocess.DEVNULL,
    )
    return command_output.decode()
