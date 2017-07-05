from genty import genty, genty_dataset

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase

@genty
class TestMasterAPIVersionRequests(BaseFunctionalTestCase):

    def _build_accept_header_with_api_version(self, version: int):
        header = 'Accept'
        value = 'application/vnd.clusterrunner.v{}+json'.format(version)
        return {header: value}

    @genty_dataset(
        no_accept_header=(None, 1),
        v1_accept_header=(1, 1),
        v2_accept_header=(2, 2),
        invalid_version_accept_header=(999, 1),
    )
    def test_api_version_with_accept_header(self, version: int, exp_version: int):
        master = self.cluster.start_master()
        version_url = master._api.url('version')
        header = self._build_accept_header_with_api_version(version) if version else None
        resp = master._network.get(version_url, headers=header).json()
        self.assertEqual(resp['api_version'], exp_version)
