import os
import shutil
import tarfile
import tempfile
import zipfile

from app.util.process_utils import Popen_with_delayed_expansion


def async_delete(path):
    """
    Asynchronously delete a file or a directory. This functionality is handy for deleting large directories.
    For example, in ClusterRunner, deleting the results directory can take up to half an hour. With async_delete(),
    the delete call will return almost immediately.

    Under the covers, this is implemented by first synchronously renaming the file or directory to a unique name
    inside of a temporary directory. After that, we launch an asynchronous process that deletes that file/directory.
    This asynchronous process does not die when the invoking process (this process) exits/dies.

    :param path: the absolute path to the file or directory to asynchronously delete
    :type path: str
    """
    new_temp_path = tempfile.mkdtemp(prefix='async_delete_directory')
    shutil.move(path, new_temp_path)
    # TODO: make the following command cross-platform.
    Popen_with_delayed_expansion(['rm', '-rf', new_temp_path])


def create_dir(dir_path, mode=None):
    """
    Create a directory. If it already exists, allow it and swallow the exception.

    :param dir_path: the directory to create
    :type dir_path: str
    :param mode: the permissions to set dir_path to (ie: 0o700)
    :type mode: int(octal)|None
    """
    try:
        # Unfortunately, the exists_ok parameter does not do what it's supposed to do.
        os.makedirs(dir_path, exist_ok=True)
    except FileExistsError:
        pass

    if mode is not None:
        os.chmod(dir_path, mode)


def write_file(file_contents, file_path):
    """
    Write a string or byte string to a file.

    :param file_contents: The string or byte string to write
    :type file_contents: str | bytes
    :param file_path: The path of the file to write
    :type file_path: str
    """
    file_dir, _ = os.path.split(file_path)
    create_dir(file_dir)

    if isinstance(file_contents, bytes):
        open_kwargs = {}
        file_mode = 'wb'
    else:
        open_kwargs = {'encoding': 'utf-8'}  # This is necessary since UTF-8 is not the default on all systems.
        file_mode = 'w'

    with open(file_path, file_mode, **open_kwargs) as f:
        f.write(file_contents)


def extract_tar(archive_file, target_dir=None, delete=False):
    """

    :param archive_file:
    :type archive_file:
    :param target_dir:
    :type target_dir:
    :param delete:
    :type delete:
    :return:
    :rtype:
    """
    if not target_dir:
        target_dir, _ = os.path.split(archive_file)  # default to same directory as tar file

    if not tarfile.is_tarfile(archive_file):
        raise Exception("Not a tarfile: {}".format(archive_file))

    try:
        with tarfile.open(archive_file, 'r:gz') as f:
            f.extractall(target_dir)
    finally:
        if delete:
            os.remove(archive_file)


def tar_directory(target_dir: str, archive_filename: str) -> str:
    """
    Tar up the specified directory.
    :param target_dir: directory whose contents to tar up and where the tar file will be created
    :param archive_filename: name of the tar file
    :return: path to the created tar file
    """
    tar_file = os.path.join(
        target_dir,
        archive_filename
    )
    tar_directories(
        target_dirs_to_archive_paths={target_dir: '.'},
        tarfile_path=tar_file,
    )
    return tar_file


def tar_directories(target_dirs_to_archive_paths, tarfile_path):
    """
    Tar up the specified directories.
    :param target_dirs_to_archive_paths: mapping of directories to their intended path in the archive file.
    :type target_dirs_to_archive_paths: dict
    :param tarfile_path: the path of the resulting archive file
    :return:
    """
    with tarfile.open(tarfile_path, 'w:gz') as tar:
        for dir_path, archive_name in target_dirs_to_archive_paths.items():
            target_dir = os.path.normpath(dir_path)
            tar.add(target_dir, arcname=archive_name)
    # Verify that the tarfile is readable
    with tarfile.open(tarfile_path) as tar:
        for member in tar.getmembers():
            with tar.extractfile(member.name) as target:
                data = target.read()


def zip_directory(target_dir: str, archive_filename: str) -> str:
    """
    Zip up the specified directory and stick the resulting zip file in that directory.
    :param target_dir: the directory to zip and the location of the resulting zip file
    :param archive_filename: filename for the created zip file
    :return: the full path to the created zip archive file
    """
    # Create the archive in a temp location and then move it to the target dir.
    # (Otherwise the resulting archive will include an extra zero-byte file.)
    target_path = os.path.join(target_dir, archive_filename)
    with tempfile.TemporaryDirectory() as temp_dirpath:
        tmp_zip_filename = os.path.join(temp_dirpath, 'clusterrunner_tmp__' + archive_filename)
        with zipfile.ZipFile(tmp_zip_filename, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(target_dir):
                for filename in filenames:
                    path = os.path.normpath(os.path.join(dirpath, filename))
                    if os.path.isfile(path):
                        relpath = os.path.relpath(path, target_dir)
                        zf.write(path, relpath)
        shutil.move(tmp_zip_filename, target_path)
    return target_path


def unzip_directory(archive_file: str, target_dir: str=None, delete: bool=False):
    """
    Extract the specified zip file.
    :param archive_file: the zip archive file to extract
    :param target_dir: the directory in which to extract; defaults to same as archive file
    :param delete: whether to delete the zip archive file after unpacking
    """
    if not target_dir:
        target_dir, _ = os.path.split(archive_file)  # default to same directory as archive file

    shutil.unpack_archive(archive_file, target_dir, 'zip')

    if delete:
        os.remove(archive_file)
