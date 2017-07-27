from typing import Optional

from genty import genty, genty_dataset
import tornado.httpserver
from unittest.mock import ANY, call, MagicMock

from app.util.conf.configuration import Configuration
from app.web_framework.cluster_application import ClusterApplication
from app.web_framework.cluster_base_handler import ClusterBaseHandler, ClusterBaseAPIHandler
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterBaseHandler(BaseUnitTestCase):

    _PAGINATION_OFFSET = 0
    _PAGINATION_LIMIT = 20
    _PAGINATION_MAX_LIMIT = 200

    def setUp(self):
        super().setUp()
        Configuration['pagination_offset'] = self._PAGINATION_OFFSET
        Configuration['pagination_limit'] = self._PAGINATION_LIMIT
        Configuration['pagination_max_limit'] = self._PAGINATION_MAX_LIMIT

    @genty_dataset(
        when_request_contains_no_origin_header=(None, '.*'),
        when_cors_conf_value_has_not_been_set=('http://alice.in-wonder.land:8080', None),
        when_request_origin_is_not_allowed=('http://alice.in-wonder.land:8080', 'http://bill\.in-wonder\.land:\d*'),
    )
    def test_set_default_headers_should_not_set_access_control_headers(self, request_origin, cors_conf_value):
        mock_application = MagicMock(spec_set=ClusterApplication())
        mock_request = MagicMock(spec=tornado.httpserver.HTTPRequest('GET', '/v1/versions'), headers={})
        if cors_conf_value:
            Configuration['cors_allowed_origins_regex'] = cors_conf_value
        if request_origin:
            mock_request.headers['Origin'] = request_origin

        handler = ClusterBaseAPIHandler(mock_application, mock_request)
        handler.set_header = MagicMock()
        handler.set_default_headers()

        any_set_access_control_origin_call = call('Access-Control-Allow-Origin', ANY)
        any_set_access_control_headers_call = call('Access-Control-Allow-Headers', ANY)
        any_set_access_control_methods_call = call('Access-Control-Allow-Methods', ANY)

        self.assertNotIn(any_set_access_control_origin_call, handler.set_header.call_args_list,
                         'set_default_headers() should not set the Access-Control-Allow-Origin header.')

        self.assertNotIn(any_set_access_control_headers_call, handler.set_header.call_args_list,
                         'set_default_headers() should not set the Access-Control-Allow-Headers header.')

        self.assertNotIn(any_set_access_control_methods_call, handler.set_header.call_args_list,
                         'set_default_headers() should not set the Access-Control-Allow-Methods header.')

    @genty_dataset(
        when_request_origin_is_allowed=('http://alice.in-wonder.land:8080', 'http://[^.]*\.in-wonder\.land'),
    )
    def test_set_default_headers_should_set_access_control_headers(self, request_origin, cors_conf_value):
        mock_application = MagicMock(spec_set=ClusterApplication())
        mock_request = MagicMock(spec=tornado.httpserver.HTTPRequest('GET', '/v1/versions'), headers={})
        Configuration['cors_allowed_origins_regex'] = cors_conf_value
        mock_request.headers['Origin'] = request_origin

        handler = ClusterBaseAPIHandler(mock_application, mock_request)
        handler.set_header = MagicMock()
        handler.set_default_headers()

        expected_set_access_control_origin_call = call('Access-Control-Allow-Origin', request_origin)
        expected_set_access_control_headers_call = call(
            'Access-Control-Allow-Headers',
            'Content-Type, Accept, X-Requested-With, Session, Session-Id',
        )
        expected_set_access_control_methods_call = call(
            'Access-Control-Allow-Methods',
            'GET',
        )

        self.assertIn(expected_set_access_control_origin_call, handler.set_header.call_args_list,
                      'set_default_headers() should not set the Access-Control-Allow-Origin header.')

        self.assertIn(expected_set_access_control_headers_call, handler.set_header.call_args_list,
                      'set_default_headers() should not set the Access-Control-Allow-Headers header.')

        self.assertIn(expected_set_access_control_methods_call, handler.set_header.call_args_list,
                      'set_default_headers() should not set the Access-Control-Allow-Methods header.')

    @genty_dataset(
        no_params=(None, None, _PAGINATION_OFFSET, _PAGINATION_LIMIT),
        offset_param=(50, None, 50, _PAGINATION_LIMIT),
        limit_param=(None, 50, _PAGINATION_OFFSET, 50),
        offset_and_limit_param=(50, 100, 50, 100),
        negative_offset_param=(-50, None, 0, _PAGINATION_LIMIT),
        negative_limit_param=(None, -50, _PAGINATION_OFFSET, 0),
    )
    def test_validate_pagination_params(
            self,
            offset: Optional[int],
            limit: Optional[int],
            expected_offset: int,
            expected_limit: int,
            ):
        actual_offset, actual_limit = ClusterBaseHandler._validate_pagination_params(offset, limit)
        self.assertEqual(actual_offset, expected_offset, 'Actual offset does not match expected offset')
        self.assertEqual(actual_limit, expected_limit, 'Actual limit does not match expected limit')
