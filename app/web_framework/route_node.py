import inspect
from typing import Optional, List


class RouteNode(object):
    """
    A tree data structure for representing the parts of a url path, for routing.
    """
    def __init__(self, regex_part: str, handler: type, label: Optional[str]=None, version: Optional[int]=None):
        """
        :param regex_part: To generate the regex the web framework will use to match this route, we combine
        a set of regex_parts: The regex_part in this node and the regex_parts in all its ancestor nodes.
        :param handler: The handler class that will be instantiated by the web framework when this route is hit.
        :param label: A human-friendly label for the objects returned by this route, ie "builds"
        :param version: The API version assigned to this route
        """
        self.label = label or regex_part
        self.regex_part = regex_part
        self.handler = handler
        self.children = list()
        self.parent = None
        self.version = version

    def regex(self):
        """
        The route's regex, used to register this route with the web framework
        :rtype: str
        """
        ancestor_regex_parts = [ancestor.regex_part.rstrip('/') for ancestor in list(reversed(self.ancestors()))]
        return r'/'.join(ancestor_regex_parts + [self.regex_part]).rstrip('/') + '/?'

    def route_template(self):
        """
        The generic form of this route, for display in the API 'child routes'
        :rtype: str
        """
        ancestor_names = [ancestor.name().rstrip('/') for ancestor in list(reversed(self.ancestors()))]
        return '/'.join(ancestor_names + [self.name()])

    def name(self):
        """
        The 'name' property of this route is derived from the regex defined and the handler's method params
        :rtype: str
        """
        # If we are dealing with a capturing regex, the name of this route should correspond to the last argument name
        # for the handler's get() method
        if self.regex_part.startswith('('):
            if hasattr(self.handler, 'get'):
                get_params = inspect.getargspec(self.handler.get).args  # pylint: disable=deprecated-method
                if len(get_params) > 1:
                    return '[{}]'.format(get_params[-1])
        return self.regex_part

    def add_children(self, child_nodes: List['RouteNode'], version: Optional[int]=None) -> 'RouteNode':
        """
        Build the tree structure by adding child RouteNodes to this RouteNode.  Can be chained.
        :param version: The API version assigned to all children routes
        """
        self.children += child_nodes
        for node in child_nodes:
            node.parent = self
            if version is not None:
                node.assign_version_to_all_children(version)
        return self

    def get_children(self, version: int) -> List['RouteNode']:
        """
        Get all children routes that have the same version as requested.
        :param version: The requested version.
        """
        return [child for child in self.children if child.version == version]

    def assign_version_to_all_children(self, version: int):
        """
        Recursively assigns an API version to the current child and all of its direct children.
        """
        self.version = version
        for node in self.children:
            node.assign_version_to_all_children(version)

    def ancestors(self):
        """
        Recursively finds parents and returns them
        :rtype: list[RouteNode]
        """
        if self.parent is None:
            return list()
        parent_ancestors = self.parent.ancestors() or []
        return [self.parent] + parent_ancestors

    def descendants(self):
        """
        Recursively finds children and returns them
        :rtype: list[RouteNode]
        """
        descendants = list(self.children)
        for child in self.children:
            descendants += child.descendants()
        return descendants
