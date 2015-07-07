from app.common.console_output_segment import ConsoleOutputSegment


class ConsoleOutput(object):
    """
    Represents the console output of an atom.
    """
    def __init__(self, path):
        """
        :param path: sys path to the console output file
        :type path: str
        """
        self.path = path

    def segment(self, max_lines=50, offset_line=None):
        """
        Return a segment of the console output.

        :type max_lines: int
        :param offset_line: The starting line number in the console output from which the segment should
            return content for. If set to None, then reads content starting from the end.
        :type offset_line: int | None
        :rtype: ConsoleOutputSegment
        """
        if offset_line is None:
            return self._parse_from_end(max_lines)
        else:
            return self._parse_from_offset(max_lines, offset_line)

    def _parse_from_offset(self, max_lines, offset_line):
        """
        Return up to max_lines of output starting from line number offset_line. If max_lines + offset_line
        doesn't exist on this console output, then return everything beyond offset_line.

        :type max_lines: int
        :type offset_line: int
        :rtype: ConsoleOutputSegment
        """
        total_lines = 0
        output_lines = 0
        console_output = []

        with open(self.path, 'r', encoding='utf-8', errors='replace') as f:
            # Iterate up to the index offset_line
            for i in range(0, offset_line):
                # This is an error, meaning that there aren't even offset_line+1 lines in self.path.
                if f.readline() == '':
                    raise ValueError('offset: {} is higher than the total number of lines in file {}'.format(
                        offset_line, self.path))

                total_lines += 1

            # Retrieve the console_output just between offset_line and offset_line + max_lines
            for i in range(offset_line, offset_line + max_lines):
                line = f.readline()

                # We have reached the end of the file, or a line that has not finished being written to.
                if line == '' or not line.endswith("\n"):
                    break

                console_output.append(line)
                output_lines += 1
                total_lines += 1

            # If there are more lines, then keep on counting in order to populate total_lines properly
            while f.readline():
                total_lines += 1

        return ConsoleOutputSegment(offset_line, output_lines, total_lines, ''.join(console_output))

    def _parse_from_end(self, max_lines):
        """
        Return console output segment containing the last max_lines of output, or the whole file
        if less than or equal to max_lines.

        :type max_lines: int
        :rtype: ConsoleOutputSegment
        """
        total_lines = 0
        output_lines = 0
        console_output = []

        with open(self.path, 'r', encoding='utf-8', errors='replace') as f:
            # Figure out how many lines there are, so that we know which offset line to start appending
            # console output from.
            for line in f:
                if line.endswith("\n"):
                    total_lines += 1

            f.seek(0)
            offset_line = max(total_lines - max_lines, 0)

            # Move file pointer to the desired offset_line
            for i in range(offset_line):
                f.readline()

            for i in range(offset_line, total_lines):
                console_output.append(f.readline())
                output_lines += 1

        return ConsoleOutputSegment(offset_line, output_lines, total_lines, ''.join(console_output))
