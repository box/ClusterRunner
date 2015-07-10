from cx_Freeze import setup, Executable
import os
from os.path import dirname, join
import subprocess
import sys

from app.util import autoversioning
from app.util.process_utils import is_windows


buildOptions = {
    'excludes': [],
    'append_script_to_exe': False,
    'build_exe': 'dist',
    'compressed': True,
    'copy_dependent_files': True,
    'create_shared_zip': True,
    'include_in_shared_zip': True,
    'include_files': [
        ('bin/git_askpass.sh', 'bin/git_askpass.sh'),
        ('bin/git_ssh.sh', 'bin/git_ssh.sh'),
        ('conf/default_clusterrunner.conf', 'conf/default_clusterrunner.conf'),
    ],
    'optimize': 1,  # This should not be set to 2 because that removes docstrings needed for command line help.
}

base = 'Console'

executable_name = 'clusterrunner.exe' if is_windows() else 'clusterrunner'
executables = [
    Executable('main.py', base=base, targetName=executable_name)
]

if sys.platform.startswith('linux'):
    # Fixes compatibility between rhel and ubuntu
    bin_includes = ['/usr/lib64/libssl.so.10', '/usr/lib64/libcrypto.so.10']
    file_exists = [os.path.isfile(filename) for filename in bin_includes]

    if all(file_exists):
        buildOptions['bin_includes'] = bin_includes

version = autoversioning.get_version()
autoversioning.write_package_version_file(version)

setup(name='ClusterRunner',
      version=version,
      description='',
      options=dict(build_exe=buildOptions),
      executables=executables)

autoversioning.restore_original_package_version_file()

if sys.platform == 'darwin':
    # Fix a cx_freeze issue on mac.
    # (See similar fix at https://bitbucket.org/iep-project/iep/commits/1e845c0f35)
    abs_python_path = None
    clusterrunner_path = join(dirname(__file__), 'dist', executable_name)

    # Get the Python reference in clusterrunner
    otool_proc = subprocess.Popen(('otool', '-L', clusterrunner_path), stdout=subprocess.PIPE)
    clusterrunner_libs = otool_proc.stdout.readlines()
    for lib in clusterrunner_libs[1:]:
        lib = lib.decode().strip()
        lib_filename, _ = lib.split(maxsplit=1)
        if lib_filename.endswith('/Python'):
            abs_python_path = lib_filename

    # Replace the absolute path reference in clusterrunner with a relative path
    if abs_python_path:
        rel_python_path = '@executable_path/Python'
        print('Replacing reference: "{}" -> "{}"'.format(abs_python_path, rel_python_path))
        subproc_args = ['install_name_tool', '-change', abs_python_path, rel_python_path, clusterrunner_path]
        subprocess.Popen(subproc_args)
