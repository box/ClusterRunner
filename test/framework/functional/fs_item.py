import os


class FSItem(object):
    def __init__(self, name, contents):
        """
        Represents an abstract file system item (e.g., a file or directory). This is an abstract base class and should
        not be instantiated directly.

        :param name: The name of the file system item
        :type name: str
        :param contents: The contents of the file system item
        :type contents: str | list[FSItem]
        """
        self.name = name
        self.contents = contents

    def assert_matches_path(self, path, allow_extra_items=False):
        """
        Compare an expected file system structure specified by this FSItem name and contents tree to an actual path on
        the local filesystem. For Directory-type FSItems, this makes a recursive assert call to each FSItem in the
        contents attribute. This raises an FSAssertionFailure if a mismatch is found.

        :param path: The real filesystem path to compare this FSItem against
        :type path: str
        :param allow_extra_items: Whether or not to raise an FSAssertionFailure if files are found in the filesystem
            that were not explicitly specified in the FSItem tree
        :type allow_extra_items: bool
        """
        if not os.path.exists(path):
            raise FSAssertionError('Path "{}" does not exist.'.format(path))

        if self.name != os.path.basename(path):
            raise FSAssertionError('Path "{}" does not match the expected name of "{}".'.format(path, self.name))

        self._assert_specific_type_matches_path(path, allow_extra_items)

    def _assert_specific_type_matches_path(self, path, allow_extra_items):
        """
        This method contains code to do type-specific assertions (e.g., assertions specific to File or Directory types
        of FSItems). Subclasses should override this method.

        :type path: str
        :type allow_extra_items: bool
        """
        raise NotImplementedError


class Directory(FSItem):
    def __init__(self, name, contents=None):
        """
        :param name: The name of the directory
        :type name: str
        :param contents: The contents of the directory as a list of FSItems, or None for no contents
        :type contents: list[FSItem]
        """
        contents = contents or []
        super().__init__(name, contents)

    def _assert_specific_type_matches_path(self, path, allow_extra_items):
        """
        Compare the name and conents specified by this Directory instance to an actual directory on the local
        filesystem. This makes a recursive assert call to each FSItem in the contents attribute to also verify items in
        this directory. This raises an FSAssertionFailure if a mismatch is found.

        :param path: The real path of a directory to compare this Directory name and contents against
        :type path: str
        :param allow_extra_items: Whether or not to raise an FSAssertionFailure if files are found in the filesystem
            that were not explicitly specified in self.contents of this instance
        :type allow_extra_items: bool
        """
        if not os.path.isdir(path):
            raise FSAssertionError('Path "{}" is not a directory.'.format(path))

        extra_items = os.listdir(path)
        for fs_item in self.contents:
            subpath = os.path.join(path, fs_item.name)
            fs_item.assert_matches_path(subpath, allow_extra_items)
            extra_items.remove(fs_item.name)  # No need to catch ValueError here since we know subpath exists.

        if extra_items and not allow_extra_items:
            raise FSAssertionError('Directory "{}" had unexpected items: {}'.format(path, extra_items))


class File(FSItem):
    def __init__(self, name, contents=None):
        """
        :param name: The name of the file
        :type name: str
        :param contents: The contents of the file as a string, or None to skip content validation
        :type contents: str
        """
        super().__init__(name, contents)

    def _assert_specific_type_matches_path(self, path, allow_extra_items):
        """
        Compare the name and contents specified by this File instance to an actual file on the local filesystem. This
        raises an FSAssertionFailure if a mismatch is found.

        :param path: The real path of a file to compare this File name and contents against
        :type path: str
        :param allow_extra_items: [Unused for File type]
        :type allow_extra_items: bool
        """
        if not os.path.isfile(path):
            raise FSAssertionError('Path "{}" is not a file.'.format(path))

        if self.contents is not None:
            with open(path) as f:
                actual_file_contents = f.read()

            if actual_file_contents != self.contents:
                raise FSAssertionError('File "{}" contents did not match expected contents.\nExpected:\n"{}"\n'
                                       'Actual:\n"{}"'.format(path, self.contents, actual_file_contents))


class FSAssertionError(AssertionError):
    """
    Represents a mismatch found between an FSItem tree (the expected file system structure) and the actual file system.
    """
