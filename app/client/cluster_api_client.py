from urllib import parse

from typing import Any, Callable, Dict, List, Optional

from app.manager.build import BuildStatus
from app.util.conf.configuration import Configuration
from app.util import log, poll
from app.util.network import Network
from app.util.secret import Secret
from app.util.url_builder import UrlBuilder


class ClusterAPIClient(object):
    """
    This is the base class for REST API wrappers around the manager and worker services.
    """
    def __init__(self, base_api_url):
        """
        :param base_api_url: The base API url of the service (e.g., 'http(s)://localhost:43000')
        :type base_api_url: str
        """
        self._api = UrlBuilder(self._ensure_url_has_scheme(base_api_url))
        self._network = Network()
        self._logger = log.get_logger(__name__)

    def _ensure_url_has_scheme(self, url):
        """
        If url does not start with 'http' or 'https', add 'http://' or 'https://' at the beginning.
        :type url: str
        :rtype: str
        """
        url = url.strip()
        if not url.startswith('http'):
            url = '{}://{}'.format(Configuration['protocol_scheme'], url)
        return url


class ClusterManagerAPIClient(ClusterAPIClient):
    """
    This is a light wrapper client around the ClusterManager REST API.
    """
    # TODO: Refactor BuildRunner to use this class.
    def post_new_build(self, request_params):
        """
        Send a post request to the manager to start a new build with the specified parameters.

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
        Make a GET call to the manager to get artifact for a build.
        :param build_id: The id of the build we want to get the artifact of
        :type build_id: int
        :return: tuple of (the artifact tarball, status code)
        :rtype: tuple of (bytes, int)
        """
        artifacts_url = self._api.url('build', build_id, 'artifacts.zip')
        response = self._network.get(artifacts_url)
        return response.content, response.status_code

    def cancel_build(self, build_id):
        """
        PUT a request to the manager to cancel a build.
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
        Send a get request to the manager to get the status of the specified build.

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

    def block_until_build_started(
            self,
            build_id: int,
            timeout: int=30,
            build_in_progress_callback: Optional[Callable]=None,
    ) -> bool:
        """
        Poll the build status endpoint until the build is no longer queued.

        :param build_id: The id of the build to wait for
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :return: Whether the build was started within the timeout
        """
        return self.block_until_build_has_status(
            build_id,
            [BuildStatus.BUILDING, BuildStatus.FINISHED, BuildStatus.ERROR, BuildStatus.CANCELED],
            timeout,
            build_in_progress_callback
        )

    def block_until_build_canceled(
            self,
            build_id: int,
            timeout: int=30,
            build_in_progress_callback: Optional[Callable]=None,
    ) -> bool:
        """
        Poll the build status endpoint until the build is in CANCELED state.

        :param build_id: The id of the build to wait for
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :return: Whether the build is in CANCELED state
        """
        return self.block_until_build_has_status(
            build_id,
            [BuildStatus.CANCELED],
            timeout,
            build_in_progress_callback
        )

    def block_until_build_finished(
            self,
            build_id: int,
            timeout: int=30,
            build_in_progress_callback: Optional[Callable]=None,
    ) -> bool:
        """
        Poll the build status endpoint until the build has finished.

        :param build_id: The id of the build to wait for
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :return: Whether the build was finished within the timeout
        """
        return self.block_until_build_has_status(
            build_id,
            [BuildStatus.FINISHED, BuildStatus.ERROR, BuildStatus.CANCELED],
            timeout,
            build_in_progress_callback
        )

    def block_until_build_has_status(
            self,
            build_id: int,
            build_statuses: List[str],
            timeout: int=30,
            build_in_progress_callback: Optional[Callable]=None,
    ) -> bool:
        """
        Poll the build status endpoint until the build status matches one of the specified statuses.

        :param build_id: The id of the build to wait for
        :param build_statuses: A list of build statuses which we are waiting for.
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :param build_in_progress_callback: A callback that will be called with the response data if the build has not
            yet finished. This would be useful, for example, for logging build progress.
        :return: Whether the build had one of the specified statuses within the timeout
        """
        def build_has_specified_status():
            response_data = self.get_build_status(build_id)
            build_data = response_data['build']
            if build_data['status'] in build_statuses:
                return True
            if build_in_progress_callback:
                build_in_progress_callback(build_data)
            return False

        return poll.wait_for(build_has_specified_status, timeout_seconds=timeout)

    def get_workers(self):
        """
        Return a dictionary of workers connected to the manager.
        :rtype: dict
        """
        worker_url = self._api.url('worker')
        response = self._network.get(worker_url)
        return response.json()

    def connect_worker(self, worker_url: str, num_executors: int=10) -> int:
        """
        Connect a worker to the manager. This is mostly useful for testing since real worker services
        make this call to the manager on startup.
        :param worker_url: The hostname and port of the worker, e.g., 'localhost:43001'
        :param num_executors: The number of executors for the worker
        :return: The new worker id
        """
        data = {
            'worker': worker_url,
            'num_executors': num_executors,
        }
        create_worker_url = self._api.url('worker')
        response_data = self._network.post(create_worker_url, data=data).json()
        worker_id = int(response_data['worker_id'])
        return worker_id

    def get_worker_status(self, worker_id: int) -> dict:
        """
        Send a get request to the manager to get the status of the specified worker.
        :param worker_id: The id of the worker
        :return: The API response data
        """
        worker_status_url = self._api.url('worker', worker_id)
        response_data = self._network.get(worker_status_url).json()
        return response_data['worker']

    def block_until_worker_offline(self, worker_id: int, timeout: int=None) -> bool:
        """
        Poll the build status endpoint until the build is no longer queued.
        :param worker_id: The id of the worker to wait for
        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :return: Whether the worker went offline during the timeout
        """
        def is_worker_offline():
            worker_data = self.get_worker_status(worker_id)
            return not worker_data['is_alive']

        return poll.wait_for(is_worker_offline, timeout_seconds=timeout)

    def graceful_shutdown_workers_by_id(self, worker_ids):
        """
        :type worker_ids: list[int]
        :rtype: requests.Response
        """
        return self._graceful_shutdown_workers({'workers': worker_ids})

    def graceful_shutdown_all_workers(self):
        """
        :rtype: request.Response
        """
        return self._graceful_shutdown_workers({'shutdown_all': True})

    def _graceful_shutdown_workers(self, body):
        """
        :type body: dict
        :rtype: requests.Response
        """
        shutdown_url = self._api.url('worker', 'shutdown')
        response = self._network.post_with_digest(
            shutdown_url,
            body,
            Secret.get(),
            error_on_failure=True
        )
        return response

    def get_console_output(
            self,
            build_id: int,
            subjob_id: int,
            atom_id: int,
            max_lines: int=50,
            offset: int=0,
    ) -> Dict[str, Any]:
        """Return the json-decoded response from the console output endpoint for the specified atom."""
        console_url = self._api.url('build', build_id, 'subjob', subjob_id, 'atom', atom_id, 'console')
        console_url += '?' + parse.urlencode({'max_lines': max_lines, 'offset_line': offset})
        return self._network.get(console_url).json()


class ClusterWorkerAPIClient(ClusterAPIClient):
    """
    This is a light wrapper client around the ClusterWorker REST API.
    """
    # TODO: Move the API call logic from worker.py into this class.
    def block_until_idle(self, timeout=None) -> bool:
        """
        Poll the worker executor endpoint until all executors are idle.

        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int | None
        :return: Whether the worker became idle during the timeout
        """

        return poll.wait_for(self.is_worker_idle, timeout_seconds=timeout)

    def is_worker_idle(self) -> bool:
        """
        :return: Whether worker is idle
        """
        response_data = self.get_worker_status()
        return response_data['worker']['current_build_id'] is None

    def get_worker_status(self):
        """
        Get the API status response for this worker.
        """
        worker_status_url = self._api.url()
        response_data = self._network.get(worker_status_url).json()

        if 'worker' not in response_data:
            raise ClusterAPIValidationError('Worker API response does not contain a "worker" object. URL: {}, Content:{}'
                                            .format(worker_status_url, response_data))
        return response_data


class ClusterAPIValidationError(Exception):
    """
    This represents an error during validation of an API response from a Cluster service.
    """
