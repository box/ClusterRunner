from genty import genty, genty_dataset
import tornado.httpserver
from unittest.mock import ANY, call, MagicMock

from app.util.conf.configuration import Configuration
from app.web_framework.cluster_application import ClusterApplication
from app.web_framework.cluster_base_handler import ClusterBaseHandler
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterBaseHandler(BaseUnitTestCase):

    @genty_dataset(
        when_request_contains_no_origin_header=(None, '.*'),
        when_cors_conf_value_has_not_been_set=('http://alice.in-wonder.land:8080', None),
        when_request_origin_is_not_allowed=('http://alice.in-wonder.land:8080', 'http://bill\.in-wonder\.land:\d*'),
    )
    def test_set_default_headers_should_not_set_origin_header(self, request_origin, cors_conf_value):
        mock_application = MagicMock(spec_set=ClusterApplication())
        mock_request = MagicMock(headers={})
        if cors_conf_value:
            Configuration['cors_allowed_origins_regex'] = cors_conf_value
        if request_origin:
            mock_request.headers['Origin'] = request_origin

        handler = ClusterBaseHandler(mock_application, mock_request)
        handler.set_header = MagicMock()
        handler.set_default_headers()

        any_set_origin_header_call = call('Access-Control-Allow-Origin', ANY)
        self.assertNotIn(any_set_origin_header_call, handler.set_header.call_args_list,
                         'set_default_headers() should not set the Access-Control-Allow-Origin header.')

    @genty_dataset(
        when_request_origin_is_allowed=('http://alice.in-wonder.land:8080', 'http://[^.]*\.in-wonder\.land'),
    )
    def test_set_default_headers_should_set_origin_header(self, request_origin, cors_conf_value):
        mock_application = MagicMock(spec_set=ClusterApplication())
        mock_request = MagicMock(headers={})
        Configuration['cors_allowed_origins_regex'] = cors_conf_value
        mock_request.headers['Origin'] = request_origin

        handler = ClusterBaseHandler(mock_application, mock_request)
        handler.set_header = MagicMock()
        handler.set_default_headers()

        expected_set_origin_header_call = call('Access-Control-Allow-Origin', request_origin)
        self.assertIn(expected_set_origin_header_call, handler.set_header.call_args_list,
                      'set_default_headers() should not set the Access-Control-Allow-Origin header.')
