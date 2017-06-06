from genty import genty, genty_dataset, genty_args
from tempfile import NamedTemporaryFile, TemporaryDirectory
import zipfile

from typing import Optional

from app.common.console_output import ConsoleOutput
from app.util.exceptions import BadRequestError
from test.framework.base_integration_test_case import BaseIntegrationTestCase


_INCOMPLETE_OUTPUT = '\n'.join('line_' + str(i) for i in range(10))
_COMPLETE_OUTPUT = _INCOMPLETE_OUTPUT + '\n'
_PATH_IN_ARCHIVE = 'results/output.txt'


@genty
class TestConsoleOutput(BaseIntegrationTestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_temp_plaintext_file(self, content: str) -> str:
        temp_file = NamedTemporaryFile(dir=self.temp_dir.name, delete=False)
        with temp_file as file:
            file.write(content.encode())
        return temp_file.name

    def create_temp_zip_file(self, content: str, path_in_archive: str) -> str:
        file = NamedTemporaryFile(dir=self.temp_dir.name, delete=False)
        with zipfile.ZipFile(file.name, 'w') as archive:
            archive.writestr(path_in_archive, content.encode())
        return file.name

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
            input_max_lines: int,
            input_offset_line: Optional[int],
            expected_num_lines: int,
            expected_offset_line: int,
            expected_total_num_lines: int,
            expected_content: str,
    ):
        complete_output_path = self.create_temp_plaintext_file(_COMPLETE_OUTPUT)

        console_output = ConsoleOutput.from_plaintext(complete_output_path)
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
            input_max_lines: int,
            input_offset_line: Optional[int],
            expected_num_lines: int,
            expected_offset_line: int,
            expected_total_num_lines: int,
            expected_content: str,
    ):
        incomplete_output_path = self.create_temp_plaintext_file(_INCOMPLETE_OUTPUT)

        console_output = ConsoleOutput.from_plaintext(incomplete_output_path)
        segment = console_output.segment(max_lines=input_max_lines, offset_line=input_offset_line)

        self.assertEquals(segment.num_lines, expected_num_lines)
        self.assertEquals(segment.offset_line, expected_offset_line)
        self.assertEquals(segment.total_num_lines, expected_total_num_lines)
        self.assertEquals(segment.content, expected_content)

    def test_segment_raises_value_error_if_offset_greater_than_total_length(self):
        complete_output_path = self.create_temp_plaintext_file(_COMPLETE_OUTPUT)
        console_output = ConsoleOutput.from_plaintext(complete_output_path)
        with self.assertRaises(BadRequestError):
            console_output.segment(max_lines=5, offset_line=155)

    def test_console_output_segment_with_no_offset_from_zipfile_returns_expected(self):
        complete_output_path = self.create_temp_zip_file(_COMPLETE_OUTPUT, _PATH_IN_ARCHIVE)

        console_output = ConsoleOutput.from_zipfile(complete_output_path, _PATH_IN_ARCHIVE)
        segment = console_output.segment(max_lines=3)

        self.assertEquals(segment.num_lines, 3)
        self.assertEquals(segment.offset_line, 7)
        self.assertEquals(segment.total_num_lines, 10)
        self.assertEquals(segment.content, 'line_7\nline_8\nline_9\n')

    def test_console_output_segment_with_offset_from_zipfile_returns_expected(self):
        complete_output_path = self.create_temp_zip_file(_COMPLETE_OUTPUT, _PATH_IN_ARCHIVE)

        console_output = ConsoleOutput.from_zipfile(complete_output_path, _PATH_IN_ARCHIVE)
        segment = console_output.segment(max_lines=3, offset_line=2)

        self.assertEquals(segment.num_lines, 3)
        self.assertEquals(segment.offset_line, 2)
        self.assertEquals(segment.total_num_lines, 10)
        self.assertEquals(segment.content, 'line_2\nline_3\nline_4\n')
