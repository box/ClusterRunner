import tornado.web


class ClusterApplication(tornado.web.Application):

    @staticmethod
    def get_all_handlers(root_route, default_params):
        """
        Follows a route's decendents to return all routes in a form accepted as 'handlers' by Tornado.
        :param root_route: The base RouteNode
        :type root_route: web_framework.RouteNode
        :param default_params: The params to pass to the Tornado handler
        :type default_params: dict
        :return: Tornado handler tuples
        :rtype: list [tuple (str, tornado.web.RequestHandler, dict)]
        """
        all_route_nodes = [root_route] + root_route.descendants()
        # Tornado handlers take the form of a tuple(regex, handler_class, parameters).  The parameters start with
        # the common defaults provided and we append the RouteNode we are associating each handler with
        return [(route.regex(), route.handler, dict(default_params, route_node=route)) for route in all_route_nodes]
