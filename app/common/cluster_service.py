from typing import Optional

from app.common.build_artifact import BuildArtifact
from app.util.exceptions import BadRequestError, ItemNotFoundError


class ClusterService:
    """
    The abstract base ClusterRunner service class.
    """
    def get_console_output(
            self,
            build_id: int,
            subjob_id: int,
            atom_id: int,
            result_root: str,
            max_lines: int=50,
            offset_line: Optional[int]=None,
    ):
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

        :param build_id: build id
        :param subjob_id: subjob id
        :param atom_id: atom id
        :param result_root: the sys path to either the results or artifacts directory where results are stored.
        :param max_lines: The maximum total number of lines to return. If this max_lines + offset_line lines do not
            exist in the output file, just return what there is.
        :param offset_line: The line number (0-indexed) to start reading content for. If none is specified, we will
            return the console output starting from the end of the file.
        """
        if offset_line is not None and offset_line < 0:
            raise BadRequestError('\'offset_line\' must be greater than or equal to zero.')
        if max_lines <= 0:
            raise BadRequestError('\'max_lines\' must be greater than zero.')

        segment = BuildArtifact.get_console_output(
            build_id, subjob_id, atom_id, result_root, max_lines, offset_line)

        if not segment:
            raise ItemNotFoundError('Console output does not exist on this host for '
                                    'build {}, subjob {}, atom {}.'.format(build_id, subjob_id, atom_id))
        return {
            'offset_line': segment.offset_line,
            'num_lines': segment.num_lines,
            'total_num_lines': segment.total_num_lines,
            'content': segment.content,
        }
