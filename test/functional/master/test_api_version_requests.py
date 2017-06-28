from genty import genty, genty_dataset

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase

def build_accept_header_with_api_version(version: int):
    header = 'Accept'
    value = 'application/vnd.clusterrunner.v{}+json'.format(version)
    return {header: value}

@genty
class TestMasterEndpoints(BaseFunctionalTestCase):

    @genty_dataset(
        no_accept_header=(None, 1),
        v1_accept_header=(build_accept_header_with_api_version(1), 1),
        v2_accept_header=(build_accept_header_with_api_version(2), 2),
        invalid_version_accept_header=(build_accept_header_with_api_version(999), 1),
    )
    def test_api_version_with_accept_header(self, accept_header, exp_version: int):
        # TODO: Add tests for no `v1` in URI when it gets deprecated.
        master = self.cluster.start_master()
        version_url = master._api.url('version')
        resp = master._network.get(version_url, headers=accept_header).json()
        self.assertEqual(resp['api_version'], exp_version)
