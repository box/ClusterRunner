import http.client
import re
import tornado.escape
import tornado.web

from app.util import log
from app.util.conf.configuration import Configuration
from app.util.exceptions import AuthenticationError, BadRequestError, ItemNotFoundError, ItemNotReadyError
from app.util.network import ENCODED_BODY


class ClusterBaseHandler(tornado.web.RequestHandler):

    SUCCESS_STATUS = 'SUCCESS'
    FAILURE_STATUS = 'FAILURE'

    _exception_status_codes = {
        ItemNotReadyError: http.client.ACCEPTED,
        BadRequestError: http.client.BAD_REQUEST,
        AuthenticationError: http.client.UNAUTHORIZED,
        ItemNotFoundError: http.client.NOT_FOUND,
    }

    def __init__(self, *args, **kwargs):
        self._logger = log.get_logger(__name__)
        super().__init__(*args, **kwargs)

    def initialize(self, route_node=None):
        """
        :param route_node: Each handler is associated with a RouteNode
        :type route_node: RouteNode
        """
        self._route_node = route_node

    def prepare(self):
        """
        Called at the beginning of a request before  `get`/`post`/etc.
        """
        # Decode an encoded body, if present. Otherwise fall back to decoding the raw request body. See the comments in
        # the util.network.Network class for more information about why we're doing this.
        try:
            self.encoded_body = self.get_argument(ENCODED_BODY, default=self.request.body)
            self.decoded_body = tornado.escape.json_decode(self.encoded_body) if self.encoded_body else {}

        except ValueError as ex:
            raise BadRequestError('Invalid JSON in request body.') from ex

    def get(self):
        """
        Enable GET on all endpoints by default.  Subclasses can override this without calling super().get()
        """
        self.write({})

    def write(self, response):
        """
        Inject child routes into GET requests
        :type response: dict[str, any]
        """
        if self.request.method == 'GET':
            response['child_routes'] = self.get_child_routes()
        super().write(response)

    def _write_status(self, additional_response=None, success=True, status_code=200):
        status = self.SUCCESS_STATUS if success else self.FAILURE_STATUS
        response = {'status': status}
        if additional_response is not None:
            response.update(additional_response)
        self.set_status(status_code)
        self.write(response)

    def get_child_routes(self):
        """
        Returns a dictionary of child routes for this handler.  Each handler is associated with a RouteNode, which
        can have children.  If there are children for this handler's RouteNode, we get the user-friendly representation
        of each child route.
        :rtype: dict [str, str]
        """
        if self._route_node is None:
            raise RuntimeError('This handler ({}) is not associated with a RouteNode'.format(type(self).__name__))
        return {child.label: child.route_template() for child in self._route_node.children}

    def _handle_request_exception(self, ex):
        """
        This is the "catch-all" exception handler that Tornado uses to ensure exceptions are caught and a JSON response
        is always returned to the client. (Tornado's default is an HTML response.) This also contains logic to map some
        exception types to appropriate HTTP status codes. The default status code is 500 (generic server error).

        :param ex: The exception that was caught
        :type ex: Exception
        """
        # _handle_request_exception() is called in the exception handler, so we can still use logger.exception.
        self._logger.exception('Exception occurred during request to {}.', self.request.uri)
        status_code = self._exception_status_codes.get(type(ex), http.client.INTERNAL_SERVER_ERROR)
        response = {'error': str(ex)}

        self.set_status(status_code)
        self.write(response)
        self.finish()

    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json')

        request_origin = self.request.headers.get('Origin')  # usually only set when making API request from a browser
        if request_origin and self._is_request_origin_allowed(request_origin):
            self.set_header('Access-Control-Allow-Origin', request_origin)

    def _is_request_origin_allowed(self, request_origin):
        """
        Match the specified request_origin against the conf-specified regex for CORS allowed origins. If nothing has
        been specified in the conf (which is the default setting) return False.

        :param request_origin: The value of the 'Origin' header from the incoming API request
        :type request_origin: str
        :return: Whether or not we should allow the request from the given origin
        :rtype: bool
        """
        if not request_origin:
            return False

        allowed_origins_regex = Configuration['cors_allowed_origins_regex']
        if allowed_origins_regex is not None:
            self._logger.debug('Matching request origin "{}" against cors_allowed_origins_regex conf value "{}".',
                               request_origin, allowed_origins_regex)
            if re.match(allowed_origins_regex, request_origin):
                self._logger.debug('Origin "{}" allowed. Setting Access-Control-Allow-Origin header.', request_origin)
                return True

        self._logger.debug('Origin "{}" not allowed. Not setting Access-Control-Allow-Origin header.', request_origin)
        return False
