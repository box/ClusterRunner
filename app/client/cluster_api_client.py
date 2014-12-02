from app.master.build import BuildStatus
from app.util import log, poll
from app.util.network import Network
from app.util.secret import Secret
from app.util.url_builder import UrlBuilder


class ClusterAPIClient(object):
    """
    This is the base class for REST API wrappers around the master and slave services.
    """
    def __init__(self, base_api_url):
        """
        :param base_api_url: The base API url of the service (e.g., 'http://localhost:43000')
        :type base_api_url: str
        """
        self._api = UrlBuilder(base_api_url)
        self._network = Network()
        self._logger = log.get_logger(__name__)


class ClusterMasterAPIClient(ClusterAPIClient):
    """
    This is a light wrapper client around the ClusterMaster REST API.
    """
    # TODO: Refactor BuildRunner to use this class.
    def post_new_build(self, request_params):
        """
        Send a post request to the master to start a new build with the specified parameters.

        :param request_params: The build parameters to send in the post body
        :type request_params: dict
        :return: The API response data
        :rtype: dict
        """
        build_url = self._api.url('build')
        response = self._network.post_with_digest(
            build_url,
            request_params,
            Secret.get(),
            error_on_failure=True
        )
        return response.json()

    def cancel_build(self, build_id):
        """
        PUT a request to the master to cancel a build.
        :param build_id: The id of the build we want to cancel
        :type build_id: int
        :return: The API response
        :rtype: dict
        """
        build_url = self._api.url('build', build_id)
        response = self._network.put_with_digest(
            build_url,
            {'status': 'canceled'},
            Secret.get(),
            error_on_failure=True
        )
        return response.json()

    def get_build_status(self, build_id):
        """
        Send a get request to the master to get the status of the specified build.

        :param build_id: The id of the build whose status to get
        :type build_id: int
        :return: The API response data
        :rtype: dict
        """
        build_status_url = self._api.url('build', build_id)
        response_data = self._network.get(build_status_url).json()

        if 'build' not in response_data or 'status' not in response_data['build']:
            raise ClusterAPIValidationError('Status response does not contain a "build" object with a "status" value.'
                                            'URL: {}, Content:{}'.format(build_status_url, response_data))
        return response_data

    def block_until_build_finished(self, build_id, timeout=None, build_in_progress_callback=None):
        """
        Poll the build status endpoint until the build is finished or until the timeout is reached.

        :param build_id: The id of the build to wait for
        :type build_id: int
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int | None
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :type build_in_progress_callback: callable
        """
        def is_build_finished():
            response_data = self.get_build_status(build_id)
            build_data = response_data['build']
            if build_data['status'] in (BuildStatus.FINISHED, BuildStatus.ERROR, BuildStatus.CANCELED):
                return True
            if build_in_progress_callback:
                build_in_progress_callback(build_data)
            return False

        poll.wait_for(is_build_finished, timeout_seconds=timeout)


class ClusterSlaveAPIClient(ClusterAPIClient):
    """
    This is a light wrapper client around the ClusterSlave REST API.
    """
    # TODO: Move the API call logic from slave.py into this class.


class ClusterAPIValidationError(Exception):
    """
    This represents an error during validation of an API response from a Cluster service.
    """
