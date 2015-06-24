from genty import genty, genty_dataset

from app.util.process_utils import Popen_with_delayed_expansion

from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestProcessUtils(BaseUnitTestCase):

    @genty_dataset(
        str_cmd_on_windows=(
            'set FOO=1 && echo !FOO!',
            'nt',
            ['cmd', '/V', '/C', 'set FOO=1 && echo !FOO!'],
        ),
        list_cmd_on_windows=(
            ['set', 'FOO=1', '&&', 'echo', '!FOO!'],
            'nt',
            ['cmd', '/V', '/C', 'set', 'FOO=1', '&&', 'echo', '!FOO!'],
        ),
        str_cmd_on_posix=(
            'export FOO=1; echo $FOO',
            'posix',
            'export FOO=1; echo $FOO',
        ),
        list_cmd_on_posix=(
            ['export', 'FOO=1;', 'echo', '$FOO'],
            'posix',
            ['export', 'FOO=1;', 'echo', '$FOO'],
        ),
    )
    def test_Popen_with_deplayed_expansion(self, input_cmd, os_name, expected_final_cmd):
        # Arrange
        mock_os = self.patch('app.util.process_utils.os')
        mock_os.name = os_name
        mock_subprocess_popen = self.patch('subprocess.Popen')

        # Act
        Popen_with_delayed_expansion(input_cmd)

        # Assert
        mock_subprocess_popen.assert_called_once_with(expected_final_cmd)
