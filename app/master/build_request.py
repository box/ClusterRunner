"""
This class is a data object for the build request parameters provided by the user. It additionally provides
validation.

A requirement with the request that it must be able to specify where the cluster runner configuration file
is going to live (clusterrunner.yaml). The cluster runner will look in the top level project directory
for this file. If it doesn't exist, it is a fatal error and the build will be immediately aborted.

The only field that is consistently required for ALL types is the "type" field.

Possible formats of valid incoming build requests:

Git repo:
{
    "type": "repo",
    "repo": "http://dduke:password1234@github.com/drobertduke/some-project",
    [OPTIONAL] "hash": "123456789123456789123456789"
}

Adhoc (arbitrary shell commands):
{
    "type": "adhoc",
    "commands": [
        "cd /box/www/current",
        "git fetch scm",
        "git reset --hard 123456789123456789123456789"
    ],
    "project_directory": "/box/www/current"
}
"""

from app.util import util


class BuildRequest(object):

    def __init__(self, build_parameters):
        """
        :param build_parameters: A dictionary of request parameters
        :type build_parameters: dict[str, str]
        """
        self._build_parameters = dict(build_parameters) or {}

        build_type = self._build_parameters.get('type')
        self._build_type = build_type.lower() if build_type else None

    def is_valid(self):
        """
        Validate the request arguments to make sure that they have provided enough information and are valid.

        :return: whether the parameters are valid or not
        :rtype: bool
        """
        missing_parameters = set(self.required_parameters()) - self._build_parameters.keys()
        return self.is_valid_type() and not missing_parameters

    def is_valid_type(self):
        """
        :return: whether the type is valid or not
        :rtype: bool
        """
        return util.get_project_type_subclass(self._build_type) is not None

    def required_parameters(self):
        """
        :return: a list of the required parameters for this type of build
        :rtype: list[str]
        """
        project_type_class = util.get_project_type_subclass(self._build_type)
        if project_type_class:
            return project_type_class.required_constructor_argument_names()

        return []

    def build_parameters(self):
        """
        :return: the build parameters
        :rtype: dict
        """
        return self._build_parameters
