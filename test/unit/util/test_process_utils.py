from genty import genty, genty_dataset, genty_args

from app.util.process_utils import Popen_with_delayed_expansion, get_environment_variable_setter_command

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

    @genty_dataset(
        windows=genty_args(
            name='FOO',
            value='1',
            os_name='nt',
            expected_command='set FOO=1&&',
        ),
        posix=genty_args(
            name='BAR',
            value='2',
            os_name='posix',
            expected_command='export BAR="2";',
        ),
    )
    def test_get_environment_variable_setter_command(self, name, value, os_name, expected_command):
        # Arrange
        mock_os = self.patch('app.util.process_utils.os')
        mock_os.name = os_name

        # Act
        command = get_environment_variable_setter_command(name, value)

        # Assert
        self.assertEqual(command, expected_command)
