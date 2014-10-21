from app.util.url_builder import UrlBuilder
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestUrlBuilder(BaseUnitTestCase):

    def test_url_should_generate_correct_url(self):
        host = 'master:9000'
        first, second, third = 'first', 'second', 'third'
        builder = UrlBuilder(host)
        url = builder.url(first, second, third)
        self.assertEqual('http://{}/v1/{}/{}/{}'.format(host, first, second, third), url,
                         'Url generated did not match expectation')
