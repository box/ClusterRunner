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
        self._api = UrlBuilder(self._ensure_url_has_scheme(base_api_url))
        self._network = Network()
        self._logger = log.get_logger(__name__)

    def _ensure_url_has_scheme(self, url):
        """
        If url does not start with 'http' or 'https', add 'http://' to the beginning.
        :type url: str
        :rtype: str
        """
        url = url.strip()
        if not url.startswith('http'):
            url = 'http://' + url
        return url


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

    def get_build_artifacts(self, build_id):
        """
        Make a GET call to the master to get artifact for a build.
        :param build_id: The id of the build we want to get the artifact of
        :type build_id: int
        :return: tuple of (the artifact tarball, status code)
        :rtype: tuple of (bytes, int)
        """
        artifacts_url = self._api.url('build', build_id, 'artifacts.tar.gz')
        response = self._network.get(artifacts_url)
        return response.content, response.status_code

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

    def block_until_build_started(self, build_id, timeout=None, build_in_progress_callback=None):
        """
        Poll the build status endpoint until the build is no longer queued.

        :param build_id: The id of the build to wait for
        :type build_id: int
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int | None
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :type build_in_progress_callback: callable
        """
        self.block_until_build_status(
            build_id,
            [BuildStatus.BUILDING, BuildStatus.FINISHED, BuildStatus.ERROR, BuildStatus.CANCELED],
            timeout,
            build_in_progress_callback
        )

    def block_until_build_finished(self, build_id, timeout=None, build_in_progress_callback=None):
        """
        Poll the build status endpoint until the build has finished.

        :param build_id: The id of the build to wait for
        :type build_id: int
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int | None
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :type build_in_progress_callback: callable
        """
        self.block_until_build_status(
            build_id,
            [BuildStatus.FINISHED, BuildStatus.ERROR, BuildStatus.CANCELED],
            timeout,
            build_in_progress_callback
        )

    def block_until_build_status(self, build_id, build_statuses, timeout=None, build_in_progress_callback=None):
        """
        Poll the build status endpoint until the build status matches a set of allowed statuses

        :param build_id: The id of the build to wait for
        :type build_id: int
        :param build_statuses: A list of build statuses which we are waiting for.
        :type build_statuses: list[str]
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int | None
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :type build_in_progress_callback: callable
        """
        def is_build_finished():
            response_data = self.get_build_status(build_id)
            build_data = response_data['build']
            if build_data['status'] in build_statuses:
                return True
            if build_in_progress_callback:
                build_in_progress_callback(build_data)
            return False

        poll.wait_for(is_build_finished, timeout_seconds=timeout)

    def get_slaves(self):
        """
        Return a dictionary of slaves connected to the master.
        :rtype: dict
        """
        slave_url = self._api.url('slave')
        response = self._network.get(slave_url)
        return response.json()

    def graceful_shutdown_slaves_by_id(self, slave_ids):
        """
        :type slave_ids: list[int]
        :rtype: requests.Response
        """
        return self._graceful_shutdown_slaves({'slaves': slave_ids})

    def graceful_shutdown_all_slaves(self):
        """
        :rtype: request.Response
        """
        return self._graceful_shutdown_slaves({'shutdown_all': True})

    def _graceful_shutdown_slaves(self, body):
        """
        :type body: dict
        :rtype: requests.Response
        """
        shutdown_url = self._api.url('slave', 'shutdown')
        response = self._network.post_with_digest(
            shutdown_url,
            body,
            Secret.get(),
            error_on_failure=True
        )
        return response


class ClusterSlaveAPIClient(ClusterAPIClient):
    """
    This is a light wrapper client around the ClusterSlave REST API.
    """
    # TODO: Move the API call logic from slave.py into this class.
    def block_until_idle(self, timeout=None):
        """
        Poll the slave executor endpoint until all executors are idle.

        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int | None
        """
        def is_slave_idle():
            response_data = self.get_slave_status()
            return response_data['slave']['current_build_id'] is None

        poll.wait_for(is_slave_idle, timeout_seconds=timeout)

    def get_slave_status(self):
        """
        Get the API status response for this slave.
        """
        slave_status_url = self._api.url()
        response_data = self._network.get(slave_status_url).json()

        if 'slave' not in response_data:
            raise ClusterAPIValidationError('Slave API response does not contain a "slave" object. URL: {}, Content:{}'
                                            .format(slave_status_url, response_data))
        return response_data


class ClusterAPIValidationError(Exception):
    """
    This represents an error during validation of an API response from a Cluster service.
    """
