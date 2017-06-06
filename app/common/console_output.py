import collections
import zipfile

from typing import BinaryIO, Optional

from app.common.console_output_segment import ConsoleOutputSegment
from app.util.exceptions import BadRequestError


class ConsoleOutput:
    """The console output of an atom"""

    @classmethod
    def from_plaintext(cls, path: str) -> 'ConsoleOutput':
        """
        :param path: Path to a plaintext file containing output
        """
        file = open(path, 'rb')
        return cls(file)

    @classmethod
    def from_zipfile(cls, zip_path: str, path_in_archive: str) -> 'ConsoleOutput':
        """
        :param zip_path: Path to a zip archive containing an output file
        :param path_in_archive: Path inside the zip archive to the file containing output
        """
        # On Windows, zip files still index their contents using Unix-style paths (since that is part
        # of the zip file spec). So we need to make sure the path in the archive is Unix-style.
        path_in_archive = path_in_archive.replace('\\', '/')
        with zipfile.ZipFile(zip_path) as build_artifact:
            file = build_artifact.open(path_in_archive)
            return cls(file)

    def __init__(self, file: BinaryIO):
        """
        This should normally only be called by static constructors.
        :param file: open handle for the file containing console output
        """
        self._file = file

    def segment(self, max_lines: int=50, offset_line: Optional[int]=None) -> ConsoleOutputSegment:
        """
        Return a segment of the console output. Note this closes the file handle so can only be called once
        per ConsoleOutput object.

        :param max_lines: The maximum number of lines of output to return
        :param offset_line: The starting line number in the console output from which the segment should
            return content for. If set to None, then reads content starting from the end.
        """
        if offset_line is None:
            return self._parse_from_end(max_lines)
        else:
            return self._parse_from_offset(max_lines, offset_line)

    def _parse_from_offset(self, max_lines: int, offset_line: int) -> ConsoleOutputSegment:
        """
        Return up to max_lines of output starting from line number offset_line. If max_lines + offset_line
        doesn't exist on this console output, then return everything beyond offset_line.
        """
        total_lines = 0
        output_lines = 0
        console_output = []

        with self._file as f:
            # Iterate up to the index offset_line
            for i in range(0, offset_line):
                # This is an error, meaning that there aren't even offset_line+1 lines in the file.
                if len(f.readline()) == 0:
                    raise BadConsoleOutputRequestError(
                        'offset {} is higher than the total number of lines: {}'.format(offset_line, total_lines))
                total_lines += 1

            # Retrieve the console_output just between offset_line and offset_line + max_lines
            for i in range(offset_line, offset_line + max_lines):
                line = f.readline()

                # We have reached the end of the file, or a line that has not finished being written to.
                if not line.endswith(b'\n'):
                    break

                console_output.append(line.decode(encoding='utf-8', errors='replace'))
                output_lines += 1
                total_lines += 1

            # If there are more lines, then keep on counting in order to populate total_lines properly
            while f.readline():
                total_lines += 1

        return ConsoleOutputSegment(offset_line, output_lines, total_lines, ''.join(console_output))

    def _parse_from_end(self, max_lines: int) -> ConsoleOutputSegment:
        """
        Return console output segment containing the last max_lines of output, or the whole file
        if less than or equal to max_lines.
        """
        total_num_lines = 0
        offset_line = 0
        console_output_lines = collections.deque()

        with self._file as f:
            for line in f:
                if not line.endswith(b'\n'):
                    break  # last line; file still (probably) being written to

                total_num_lines += 1
                console_output_lines.append(line.decode(encoding='utf-8', errors='replace'))
                if len(console_output_lines) > max_lines:
                    console_output_lines.popleft()
                    offset_line += 1

        return ConsoleOutputSegment(
            offset_line,
            len(console_output_lines),
            total_num_lines,
            ''.join(console_output_lines),
        )


class BadConsoleOutputRequestError(BadRequestError):
    """A bad request was made for console output."""
