import os
import subprocess
import sys

from app.util import fs
from app.util import package_version


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


def write_package_version_file(package_version_string):
    """
    Write the specfied version string to package_version.py. This method is intended to be called during the process of
    freezing a package for release. This in-effect hard codes the version into the frozen package.

    This also backs up the original file, which can be restored with another method in this module.

    :param package_version_string: The version to write to the file -- presumably the output of get_version()
    :type package_version_string: str
    """
    package_version_file_contents = 'version = "{}"  # DO NOT COMMIT\n'.format(package_version_string)

    os.rename(_VERSION_FILE_PATH, _VERSION_FILE_BACKUP_PATH)  # Backup the original file.
    fs.write_file(package_version_file_contents, _VERSION_FILE_PATH)


def restore_original_package_version_file():
    """
    Restore the backed up version of package_version.py. This is just a convenience method to help us remember not to
    commit changes to the package version file.
    """
    os.rename(_VERSION_FILE_BACKUP_PATH, _VERSION_FILE_PATH)


def _get_frozen_package_version():
    """
    Return the hard coded version from package_version.py. The package_version module is only populated with the actual
    version during the freeze process, so this method only returns the correct version if run from a frozen package.

    :return: The version of the (frozen) application
    :rtype: str
    """
    return package_version.version


def _calculate_source_version():
    """
    Calculate the version using a scheme based off of git repo info. Note that since this depends on the git history,
    this will *not* work from a frozen package (which does not include the git repo data). This will only work in the
    context of running the application from the cloned source code.

    :return: The version of the (source) application
    :rtype: str
    """
    global _calculated_version

    if _calculated_version is None:
        # Do the version calculation by counting number of commits in the git repo.
        commit_count_output = subprocess.check_output(
            ['git rev-list HEAD | wc -l'],
            shell=True,
            universal_newlines=True,
            cwd=os.path.dirname(__file__),
        )
        try:
            patch_version = int(commit_count_output)  # Cast to int to verify output of command was actually a number.
        except TypeError:
            patch_version = 'X'

        _calculated_version = '{}.{}'.format(_MAJOR_MINOR_VERSION, patch_version)

    return _calculated_version
