import inspect


class RouteNode(object):
    """
    A tree data structure for representing the parts of a url path, for routing.
    """
    def __init__(self, regex_part, handler, label=None, optional=False):
        """
        :param regex_part: To generate the regex the web framework will use to match this route, we combine a set of
        regex_parts: The regex_part in this node and the regex_parts in all its ancestor nodes.
        :type regex_part: str
        :param handler: The handler class that will be instantiated by the web framework when this route is hit.
        :type handler: type
        :param label: A human-friendly label for the objects returned by this route, ie "builds"
        :type label: str | None
        """
        self.label = label or regex_part
        self.regex_part = regex_part
        self.optional = optional
        self.handler = handler
        self.children = list()
        self.parent = None

    def regex(self):
        """
        The route's regex, used to register this route with the web framework
        :rtype: str
        """
        ancestor_regex_parts = []
        for ancestor in list(reversed(self.ancestors())):
            ancestor_regex = ancestor.regex_part.rstrip('/') + '/'
            if ancestor.optional:
                # Non capturing so we don't accidentally pass this as a parameter to the handlers.
                ancestor_regex = '(?:' + ancestor.regex_part.rstrip('/') + '/)?'
            ancestor_regex_parts.append(ancestor_regex)

        regex_part = self.regex_part
        if self.optional:
            regex_part = '(?:' + self.regex_part.rstrip('/') + ')?'

        return r''.join(ancestor_regex_parts + [regex_part]).rstrip('/') + '/?'

    def route_template(self, uri=None):
        """
        The generic form of this route, for display in the API 'child routes'
        :rtype: str
        """
        uri_parts = uri.split('/') if uri else []
        ancestor_names = []
        for ancestor in list(reversed(self.ancestors())):
            # If a route is marked optional, only include it in route template if its already in URI
            if ancestor.optional and ancestor.name() not in uri_parts:
                continue
            ancestor_names.append(ancestor.name().rstrip('/'))

        return '/'.join(ancestor_names + [self.name()])
        # ancestor_names = [ancestor.name().rstrip('/') for ancestor in list(reversed(self.ancestors()))]
        # return '/'.join(ancestor_names + [self.name()])

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

    def add_children(self, child_nodes):
        """
        Build the tree structure by adding child RouteNodes to this RouteNode.  Can be chained.
        :type child_nodes: list[RouteNode]
        :rtype: RouteNode
        """
        self.children += child_nodes
        for node in child_nodes:
            node.parent = self
        return self

    def get_child_routes(self, uri=None):
        """
        Get a list of all children routes for this route. If one of the child routes is marked optional
        and it doesn't appear within the requested URI, we return its children instead of it.
        :param uri: The URI of the request.
        """
        if uri is None:
            return self.children

        uri_parts = uri.split('/')
        child_routes = list()
        for child in self.children:
            if child.optional and child.name() not in uri_parts:
                child_routes += child.get_child_routes(uri)
            else:
                child_routes.append(child)
        return child_routes

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
