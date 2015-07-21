from genty import genty, genty_dataset
import os
from tempfile import mkstemp

from app.common.console_output import ConsoleOutput
from test.framework.base_integration_test_case import BaseIntegrationTestCase


@genty
class TestConsoleOutput(BaseIntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        console_output = []
        for i in range(10):
            console_output.append('line_' + str(i))

        # Completed console output file.
        cls._completed_console_output_fd, cls._completed_console_output_file_path = mkstemp()
        with open(cls._completed_console_output_file_path, 'w') as f:
            f.write("\n".join(console_output) + "\n")

        # Incomplete console output file (still being written to, as there is no newline at the end).
        cls._incomplete_console_output_fd, cls._incomplete_console_output_file_path = mkstemp()
        with open(cls._incomplete_console_output_file_path, 'w') as f:
            f.write("\n".join(console_output))

    @classmethod
    def tearDownClass(cls):
        os.close(cls._completed_console_output_fd)
        os.close(cls._incomplete_console_output_fd)
        os.remove(cls._completed_console_output_file_path)
        os.remove(cls._incomplete_console_output_file_path)

    @genty_dataset(
        happy_path_zero_offset=(5, 0, 5, 0, 10, "line_0\nline_1\nline_2\nline_3\nline_4\n"),
        happy_path_mid_offset_1=(3, 4, 3, 4, 10, "line_4\nline_5\nline_6\n"),
        happy_path_mid_offset_2=(1, 4, 1, 4, 10, "line_4\n"),
        out_of_lines_near_end_offset=(5, 7, 3, 7, 10, "line_7\nline_8\nline_9\n"),
        happy_path_no_offset_1=(5, None, 5, 5, 10, "line_5\nline_6\nline_7\nline_8\nline_9\n"),
        happy_path_no_offset_2=(1, None, 1, 9, 10, "line_9\n"),
        out_of_lines_no_offset=(200, None, 10, 0, 10,
                                "line_0\nline_1\nline_2\nline_3\nline_4\nline_5\nline_6\nline_7\nline_8\nline_9\n"),
    )
    def test_segment_for_completed_console_output(
            self,
            input_max_lines,
            input_offset_line,
            expected_num_lines,
            expected_offset_line,
            expected_total_num_lines,
            expected_content
    ):
        """
        :type input_max_lines: int
        :type input_offset_line: int | None
        :type expected_num_lines: int
        :type expected_offset_line: int
        :type expected_total_num_lines: int
        :type expected_content: str
        """
        console_output = ConsoleOutput(self._completed_console_output_file_path)
        segment = console_output.segment(max_lines=input_max_lines, offset_line=input_offset_line)

        self.assertEquals(segment.num_lines, expected_num_lines)
        self.assertEquals(segment.offset_line, expected_offset_line)
        self.assertEquals(segment.total_num_lines, expected_total_num_lines)
        self.assertEquals(segment.content, expected_content)

    @genty_dataset(
        mid_offset=(15, 5, 4, 5, 9, "line_5\nline_6\nline_7\nline_8\n"),
        no_offset=(15, None, 9, 0, 9, "line_0\nline_1\nline_2\nline_3\nline_4\nline_5\nline_6\nline_7\nline_8\n"),
        mid_lines_no_offset=(4, None, 4, 5, 9, "line_5\nline_6\nline_7\nline_8\n"),
    )
    def test_segment_for_incomplete_console_output(
            self,
            input_max_lines,
            input_offset_line,
            expected_num_lines,
            expected_offset_line,
            expected_total_num_lines,
            expected_content
    ):
        """
        :type input_max_lines: int
        :type input_offset_line: int | None
        :type expected_num_lines: int
        :type expected_offset_line: int
        :type expected_total_num_lines: int
        :type expected_content: str
        """
        console_output = ConsoleOutput(self._incomplete_console_output_file_path)
        segment = console_output.segment(max_lines=input_max_lines, offset_line=input_offset_line)

        self.assertEquals(segment.num_lines, expected_num_lines)
        self.assertEquals(segment.offset_line, expected_offset_line)
        self.assertEquals(segment.total_num_lines, expected_total_num_lines)
        self.assertEquals(segment.content, expected_content)

    def test_segment_raises_value_error_if_offset_greater_than_total_length(self):
        with self.assertRaises(ValueError):
            console_output = ConsoleOutput(self._completed_console_output_file_path)
            console_output.segment(max_lines=5, offset_line=155)
