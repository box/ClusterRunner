from typing import Tuple

import http.client
import re
import tornado.escape
import tornado.web

from app.util import log
from app.common.metrics import http_request_duration_seconds
from app.util.conf.configuration import Configuration
from app.util.exceptions import AuthenticationError, BadRequestError, ItemNotFoundError, ItemNotReadyError, PreconditionFailedError
from app.util.network import ENCODED_BODY
from app.util.session_id import SessionId
from app.web_framework.api_version_handler import APIVersionHandler


# pylint: disable=attribute-defined-outside-init
#   Handler classes are not designed to have __init__ overridden.

class ClusterBaseHandler(tornado.web.RequestHandler):
    """
    ClusterBaseHandler is the base handler for all request handlers of ClusterRunner services.
    """

    def __init__(self, *args, **kwargs):
        self._logger = log.get_logger(__name__)
        super().__init__(*args, **kwargs)

    _exception_status_codes = {
        ItemNotReadyError: http.client.ACCEPTED,
        BadRequestError: http.client.BAD_REQUEST,
        AuthenticationError: http.client.UNAUTHORIZED,
        ItemNotFoundError: http.client.NOT_FOUND,
        PreconditionFailedError: http.client.PRECONDITION_FAILED,
    }

    def initialize(self, route_node=None, **kwargs):
        """
        :param route_node: Each handler is associated with a RouteNode
        :type route_node: RouteNode
        """
        self._route_node = route_node

        accept_header = self.request.headers.get('Accept')
        uri = self.request.uri
        self.api_version = APIVersionHandler.resolve_version(accept_header, uri)

        self.set_header(APIVersionHandler.API_VERSION_HEADER_KEY, self.api_version)
        super().initialize(**kwargs)

    def _handle_request_exception(self, ex):
        """
        This is the "catch-all" exception handler that Tornado uses to map some exception types to appropriate HTTP
        status codes. The default status code is 500 (generic server error).

        :param ex: The exception that was caught
        :type ex: Exception
        """
        # Requests to access an item that isn't ready or doesn't exist shouldn't log anything.
        if not (isinstance(ex, ItemNotFoundError) or isinstance(ex, ItemNotReadyError)):
            # _handle_request_exception() is called in the exception handler, so we can still use logger.exception.
            self._logger.exception('Exception occurred during request to {}.', self.request.uri)
        status_code = self._exception_status_codes.get(type(ex), http.client.INTERNAL_SERVER_ERROR)
        self.set_status(status_code)
        self.finish()

    # For methods that annotate with `Tuple`, use `disable=invalid-sequence-index`
    # This bug is fixed in https://github.com/PyCQA/astroid/commit/563031aaf13a44adc8db4f8d0ab8020d550aae00
    # More information on the issue in https://github.com/PyCQA/pylint/issues/1212

    def get_pagination_params(self) -> Tuple[int, int]:  # pylint: disable=invalid-sequence-index
        offset = self.get_query_argument('offset', Configuration['pagination_offset'], True)
        limit = self.get_query_argument('limit', Configuration['pagination_limit'], True)
        try:
            offset = int(offset)
            limit = int(limit)
        except ValueError as ex:
            raise BadRequestError from ex
        return self._validate_pagination_params(offset, limit)

    @staticmethod
    def _validate_pagination_params(offset: int, limit: int) -> Tuple[int, int]:  # pylint: disable=invalid-sequence-index
        offset = offset if offset is not None else Configuration['pagination_offset']
        limit = limit if limit is not None else Configuration['pagination_limit']

        # A negative limit will give no results
        limit = max(limit, 0)
        offset = max(offset, 0)

        return offset, min(limit, Configuration['pagination_max_limit'])

    def on_finish(self):
        if self._route_node is not None:
            http_request_duration_seconds.labels(self.request.method,  # pylint: disable=no-member
                                                 self._route_node.regex(),
                                                 self.get_status()).observe(self.request.request_time())


class ClusterBaseAPIHandler(ClusterBaseHandler):
    """
    ClusterBaseAPIHandler is the base handler for all API endpoints that are supposed to return json responses.
    """

    SUCCESS_STATUS = 'SUCCESS'
    FAILURE_STATUS = 'FAILURE'

    def _handle_request_exception(self, ex):
        """
        Ensure exceptions are caught and a JSON response is always returned to the client.

        :param ex: The exception that was caught
        :type ex: Exception
        """
        self.write({'error': str(ex)})
        super()._handle_request_exception(ex)

    def prepare(self):
        """
        Called at the beginning of a request before  `get`/`post`/etc.
        """
        self._check_expected_session_id()
        # Decode an encoded body, if present. Otherwise fall back to decoding the raw request body. See the comments in
        # the util.network.Network class for more information about why we're doing this.
        try:
            self.encoded_body = self.get_argument(ENCODED_BODY, default=self.request.body)
            self.decoded_body = tornado.escape.json_decode(self.encoded_body) if self.encoded_body else {}

        except ValueError as ex:
            raise BadRequestError('Invalid JSON in request body.') from ex

    def _check_expected_session_id(self):
        """
        If the request has specified the session id, which is optional, and the session id does not match
        the current instance's session id, then the requester is asking for a resource that has expired and
        no longer exists.
        """
        # An expected session header in a *request* should be declared using the "Expected-Session-Id" header
        # but for legacy support an expected header can also be specified with the "Session-Id" header.
        session_id = self.request.headers.get(SessionId.SESSION_HEADER_KEY) \
            or self.request.headers.get(SessionId.EXPECTED_SESSION_HEADER_KEY)

        if session_id is not None and session_id != SessionId.get():
            raise PreconditionFailedError('Specified session id: {} has expired and is invalid.'.format(session_id))

    def options(self, *args, **kwargs):
        """
        Enable OPTIONS on all endpoints by default (preflight AJAX requests requires this).
        """
        self.write({})

    def get(self, *args, **kwargs):
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

    def write_text(self, response):
        super().set_header('Content-Type', 'text/plain; charset=utf-8')
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
        return {child.label: child.route_template() for child in self._route_node.get_children(self.api_version)}

    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json')
        self.set_header(SessionId.SESSION_HEADER_KEY, SessionId.get())

        request_origin = self.request.headers.get('Origin')  # usually only set when making API request from a browser
        if request_origin and self._is_request_origin_allowed(request_origin):
            self.set_header('Access-Control-Allow-Origin', request_origin)
            self.set_header(
                'Access-Control-Allow-Headers',
                'Content-Type, Accept, X-Requested-With, Session, Session-Id',
            )
            self.set_header('Access-Control-Allow-Methods', 'GET')

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
        if allowed_origins_regex is not None and re.match(allowed_origins_regex, request_origin):
            return True

        self._logger.debug('Origin "{}" did not match cors_allowed_origins_regex conf value of "{}". '
                           'Not setting Access-Control-Allow-Origin header.', request_origin, allowed_origins_regex)
        return False
