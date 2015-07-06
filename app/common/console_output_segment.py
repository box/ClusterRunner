class ConsoleOutputSegment(object):
    """
    Represents a subset of lines from the console output of an atom.
    """

    def __init__(self, offset_line, num_lines, total_num_lines, content):
        """
        :param offset_line: The starting line number of this console output segment.
        :type offset_line: int
        :param num_lines: The number of lines returned by this segment.
        :type num_lines: int
        :param total_num_lines: The total number of lines that are in the console output (not just this segment).
        :type total_num_lines: int
        :param content: The actual string content of this segment of console output.
        :type content: str
        """
        self.offset_line = offset_line
        self.num_lines = num_lines
        self.total_num_lines = total_num_lines
        self.content = content
