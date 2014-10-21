from box.test.genty import genty, genty_dataset
from unittest.mock import MagicMock

from app.master.job_config import JobConfig
from app.project_type.project_type import ProjectType
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestProjectType(BaseUnitTestCase):

    def test_required_constructor_args_are_correctly_detected_without_defaults(self):
        actual_required_args = _FakeEnvWithoutDefaultArgs.required_constructor_argument_names()
        expected_required_args = ['earth', 'wind', 'water', 'fire', 'heart']
        self.assertListEqual(actual_required_args, expected_required_args)

    def test_required_constructor_args_are_correctly_detected_with_defaults(self):
        actual_required_args = _FakeEnvWithDefaultArgsAndDocs.required_constructor_argument_names()
        expected_required_args = ['earth', 'wind', 'water']
        self.assertListEqual(actual_required_args, expected_required_args)

    @genty_dataset(
        arg_with_standard_doc=('earth', 'doc for earth param', True, None),
        arg_with_multiline_param_doc=('wind', 'doc for wind param...', True, None),
        arg_with_no_type_doc=('water', 'doc for water param', True, None),
        optional_arg_with_no_param_doc=('fire', None, False, 'flaming'),
        optional_arg_with_no_docs=('heart', None, False, 'bleeding'),
    )
    def test_constructor_args_info_returns_expected_data(
            self,
            arg_name,
            expected_help_string,
            expected_required_flag,
            expected_default_value,
    ):
        arguments_info = _FakeEnvWithDefaultArgsAndDocs.constructor_arguments_info()
        argument_info = arguments_info[arg_name]

        self.assertEqual(argument_info.help, expected_help_string,
                         'Actual help string should match expected.')
        self.assertEqual(argument_info.required, expected_required_flag,
                         'Actual required flag should match expected.')
        self.assertEqual(argument_info.default, expected_default_value,
                         'Actual default value for argument should match expected.')

    def test_teardown_build_runs_teardown(self):
        job_config = JobConfig('name', 'setup', 'teardown', 'command', 'atomizer', 10)
        project_type = ProjectType()
        project_type.job_config = MagicMock(return_value=job_config)
        project_type.execute_command_in_project = MagicMock(return_value=('', 0))

        project_type.teardown_build()

        project_type.execute_command_in_project.assert_called_with('teardown')

    def test_execute_command_in_project_does_not_choke_on_weird_command_output(self):
        some_weird_output = b'\xbf\xe2\x98\x82'  # the byte \xbf is invalid unicode
        mock_popen = self.patch('app.project_type.project_type.Popen').return_value
        mock_popen.communicate.return_value = (some_weird_output, None)
        mock_popen.returncode = (some_weird_output, None)

        project_type = ProjectType()
        project_type.execute_command_in_project('fake command')
        # test is successful if no exception is raised!

    @genty_dataset(
        no_blacklist=(['earth', 'wind', 'water'], None, True),
        with_blacklist=(['earth'], ['earth'], False),
        with_blacklist_others_exist=(['wind', 'water'], ['earth'], True)
    )
    def test_constructor_argument_info_with__blacklist(
            self,
            args_to_check,
            blacklist,
            expected):
        project_type = _FakeEnvWithDefaultArgsAndDocs('dirt', 'breeze', 'drop')
        arg_mapping = project_type.constructor_arguments_info(blacklist)
        for arg_name in args_to_check:
            self.assertEqual(arg_name in arg_mapping, expected)



class _FakeEnvWithoutDefaultArgs(ProjectType):
    def __init__(self, earth, wind, water, fire, heart):
        super().__init__()


class _FakeEnvWithDefaultArgsAndDocs(ProjectType):
    def __init__(self, earth, wind, water, fire='flaming', heart='bleeding'):
        """
        When your powers combine, I am... excited?
        (Note: The below parameter docs are intentionally inconsistent.)

        :param earth: doc for earth param
        :type earth: EarthObject
        :param wind: doc for wind param...
            and some other documentation we'd expect not to be exposed.
        :type wind: WindObject
        :param water: doc for water param
        :type fire: Fire Object
        :return: the captain of the planet
        :rtype: Captain
        """
        super().__init__()
