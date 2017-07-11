from genty import genty, genty_dataset
from app.web_framework.api_version_handler import APIVersionHandler

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase

@genty
class TestMasterAPIVersionRequests(BaseFunctionalTestCase):

    def _build_accept_header_with_api_version(self, version: int):
        header = 'Accept'
        value = 'application/vnd.clusterrunner.v{}+json'.format(version)
        return {header: value}

    @genty_dataset(
        no_accept_header=(None, 1, True),
        v1_accept_header=(1, 1, True),
        v2_accept_header=(2, 2, True),
        invalid_version_accept_header=(999, 1, True),
        no_accept_header_no_v1_uri=(None, APIVersionHandler.get_latest(), False),
        v1_accept_header_no_v1_uri=(1, 1, False),
        v2_accept_header_no_v1_uri=(2, 2, False),
        invalid_version_accept_header_no_v1_uri=(999, APIVersionHandler.get_latest(), False),
    )
    def test_api_version_with_accept_header(self, version: int, exp_version: int, versioned_url: bool):
        master = self.cluster.start_master()
        version_url = master._api.url('version', use_versioned_url=versioned_url)
        header = self._build_accept_header_with_api_version(version) if version else None
        resp = master._network.get(version_url, headers=header).json()
        self.assertEqual(resp['api_version'], exp_version)
