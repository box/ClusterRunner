from app.project_type.directory import Directory
from app.project_type.git import Git


_subclasses_by_name = {
    'directory': Directory,
    'git': Git,
}


def project_type_subclasses_by_name():
    """
    Return a mapping from project_type name to class.

    Note: This function cannot be placed in project_type.py because it would cause circular imports.

    :return: The ProjectType subclasses by type name
    :rtype: dict[str, type]
    """
    return _subclasses_by_name.copy()  # copy to prevent unintended modification of original


def get_project_type_subclass(project_type_name):
    """
    Given a name of an ProjectType subclass, return the class itself.

    Note: This function cannot be placed in project_type.py because it would cause circular imports.

    :param project_type_name: The name of a subclass of ProjectType (e.g., 'directory' or 'git')
    :type project_type_name: str
    :return: The ProjectType subclass corresponding to the specified type name, or None if no matching name found
    :rtype: type|None
    """
    return project_type_subclasses_by_name().get(project_type_name.lower())


def create_project_type(project_type_params):
    """
    :param project_type_params: The parameters for creating an ProjectType instance -- the dict should include the
        'type' key, which specifies the ProjectType subclass name, and key/value pairs matching constructor arguments
        for that ProjectType subclass.
    :type project_type_params: dict
    :return: The project_type instance
    :rtype: project_type.project_type.ProjectType
    """
    project_type_params = project_type_params.copy()
    project_type_name = project_type_params.pop('type')
    project_type_class = get_project_type_subclass(project_type_name)
    if project_type_class:
        return project_type_class(**project_type_params)  # create object using project_type_params as constructor args

    # Not yet implemented other project types
    return None
