import re
from urllib.parse import urljoin


class UrlBuilder(object):
    """
    Stores the host, port, scheme, and api version information for our URLs and centralizes their generation
    """
    API_VERSION_1 = 'v1'

    def __init__(self, service_address, api_version=API_VERSION_1):
        """
        :param service_address: A host and port and optional scheme, like "http://hostname.example.com:43000"
        :type service_address: str
        :type api_version: str
        """
        self._service_address = service_address
        self._api_version = api_version
        self._scheme = 'http://'

    def url(self, *args):
        """
        Produces a url given a set of paths
        :param args: A list of args to string together into a url path
        :type args: iterable [str|int]
        :rtype: str
        """
        schemed_address = self._scheme + re.sub(r'^[a-z]+://', '', self._service_address)
        versioned_url = urljoin(schemed_address, self._api_version)
        return '/'.join([versioned_url] + [str(arg).strip('/') for arg in args])
