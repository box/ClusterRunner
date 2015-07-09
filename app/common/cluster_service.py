import os

from app.common.console_output import ConsoleOutput
from app.master.build_artifact import BuildArtifact
from app.util.exceptions import BadRequestError, ItemNotFoundError


class ClusterService(object):
    """
    The abstract base ClusterRunner service class.
    """

    def get_console_output(self, build_id, subjob_id, atom_id, result_root, max_lines=50, offset_line=None):
        """
        Return the console output if it exists, raises an ItemNotFound error if not.

        On success, the response contains keys: offset_line, num_lines, total_num_lines, and content.

        e.g.:
        {
            'offset_line': 0,
            'num_lines': 50,
            'total_num_lines': 167,
            'content': 'Lorem ipsum dolor sit amet,\nconsectetur adipiscing elit,\n...',
        }

        :type build_id: int
        :type subjob_id: int
        :type atom_id: int
        :param result_root: the sys path to either the results or artifacts directory where results are stored.
        :type result_root: str
        :param max_lines: The maximum total number of lines to return. If this max_lines + offset_line lines do not
            exist in the output file, just return what there is.
        :type max_lines: int
        :param offset_line: The line number (0-indexed) to start reading content for. If none is specified, we will
            return the console output starting from the end of the file.
        :type offset_line: int | None
        """
        if offset_line is not None and offset_line < 0:
            raise BadRequestError('\'offset_line\' must be greater than or equal to zero.')
        if max_lines <= 0:
            raise BadRequestError('\'max_lines\' must be greater than zero.')

        artifact_dir = BuildArtifact.atom_artifact_directory(build_id, subjob_id, atom_id, result_root=result_root)
        output_file = os.path.join(artifact_dir, BuildArtifact.OUTPUT_FILE)

        if not os.path.isfile(output_file):
            raise ItemNotFoundError('Output file doesn\'t exist for build_id: {} subjob_id: {} atom_id: {}'.format(
                build_id, subjob_id, atom_id))

        try:
            console_output = ConsoleOutput(output_file)
            segment = console_output.segment(max_lines, offset_line)
        except ValueError as e:
            raise BadRequestError(e)

        return {
            'offset_line': segment.offset_line,
            'num_lines': segment.num_lines,
            'total_num_lines': segment.total_num_lines,
            'content': segment.content,
        }
