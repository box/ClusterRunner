import http.client
import os
import shutil
import sys
import time

from app.master.build import BuildStatus, BuildResult
import app.util.fs
from app.util.log import get_logger
from app.util.network import Network
from app.util.unhandled_exception_handler import UnhandledExceptionHandler
from app.util.url_builder import UrlBuilder
from app.client.cluster_api_client import ClusterMasterAPIClient


class BuildRunner(object):
    """
    BuildRunner is a procedure-oriented class intended to be used in the context of a script. This class provides
    functionality to synchronously execute a build on the ClusterRunner, wait for it to complete, and collect the
    build results.

    Example usage pattern:
    >>> runner = BuildRunner('http://mymaster.net:123', {'type':'git', 'url':'https://github.com/box/StatusWolf.git'})
    >>> runner.run()
    """

    API_VERSION = 'v1'

    def __init__(self, master_url, request_params, secret):
        """
        :param master_url: The url of the master which the build will be executed on
        :type master_url: str
        :param request_params: A dict of request params that will be json-encoded and sent in the build request
        :type request_params: dict
        :type secret: str
        """
        self._master_url = self._ensure_url_has_scheme(master_url)
        self._request_params = request_params
        self._secret = secret
        self._build_id = None
        self._network = Network()
        self._logger = get_logger(__name__)
        self._last_build_status_details = None
        self._master_api = UrlBuilder(master_url, self.API_VERSION)
        self._cluster_master_api_client = ClusterMasterAPIClient(master_url)

    def run(self):
        """
        Send the build request to the master, wait for the build to finish, then download the build artifacts.

        :return: Whether or not we were successful in running the build. (Note this does *not* indicate the success or
            faulure of the build itself; that is determined by the contents of the build artifacts which should be
            parsed elsewhere.)
        :rtype: bool
        """
        try:
            self._start_build()
            result = self._block_until_finished()
            self._download_and_extract_results()
            return result

        except _BuildRunnerError as ex:
            self._logger.error(str(ex))
            self._logger.warning('Script aborted due to error!')
            self._cancel_build()
            return False

    def _cancel_build(self):
        """
        Request the master cancels the build.
        """
        if self._build_id is not None:
            self._logger.warning('Cancelling build {}'.format(self._build_id))
            self._cluster_master_api_client.cancel_build(self._build_id)

    def _start_build(self):
        """
        Send the build request to the master for execution.
        """
        build_url = self._master_api.url('build')
        # todo: catch connection error
        response = self._network.post_with_digest(build_url, self._request_params, self._secret, error_on_failure=True)
        response_data = response.json()

        if 'error' in response_data:
            error_message = response_data['error']
            raise _BuildRunnerError('Error starting build: ' + error_message)

        self._build_id = response_data['build_id']

        UnhandledExceptionHandler.singleton().add_teardown_callback(self._cancel_build)
        self._logger.info('Build is running. (Build id: {})', self._build_id)

    def _block_until_finished(self, timeout=None):
        """
        Poll the build status endpoint until the build is finished or until the timeout is reached.

        :param timeout: The maximum number of seconds to wait until giving up, or None for no timeout
        :type timeout: int|None
        """
        timeout_time = time.time() + timeout if timeout else sys.maxsize
        build_status_url = self._master_api.url('build', self._build_id)
        self._logger.debug('Polling build status url: {}', build_status_url)

        while time.time() <= timeout_time:
            response = self._network.get(build_status_url)
            response_data = response.json()

            if 'build' not in response_data or 'status' not in response_data['build']:
                raise _BuildRunnerError('Status response does not contain a "build" object with a "status" value.'
                                        'URL: {}, Content:{}'.format(build_status_url, response_data))

            build_data = response_data['build']
            if build_data['status'] == BuildStatus.FINISHED:
                self._logger.info('Build is finished. (Build id: {})', self._build_id)
                completion_message = 'Build {} result was {}'.format(self._build_id, build_data['result'])
                is_success = build_data['result'] == BuildResult.NO_FAILURES
                if is_success:
                    self._logger.info(completion_message)
                else:
                    self._logger.error(completion_message)
                    if build_data['failed_atoms']:
                        self._logger.error('These atoms had non-zero exit codes (failures):')
                        for failure in build_data['failed_atoms']:
                            self._logger.error(failure)
                    return False

                return True

            if build_data['status'] == BuildStatus.ERROR:
                message = 'Build aborted due to error: {}'.format(build_data.get('error_message'))
                raise _BuildRunnerError(message)

            if build_data['status'] == BuildStatus.BUILDING:
                if build_data['details'] != self._last_build_status_details:
                    self._last_build_status_details = build_data['details']
                    self._logger.info(build_data['details'])

            time.sleep(1)

        raise _BuildRunnerError('Build timed out after {} seconds.'.format(timeout))

    def _download_and_extract_results(self, timeout=None):
        """
        Download the result files for the build.
        """
        timeout_time = time.time() + timeout if timeout else sys.maxsize

        download_artifacts_url = self._master_api.url('build', self._build_id, 'result')
        download_filepath = 'build_results/artifacts.tar.gz'
        download_dir, _ = os.path.split(download_filepath)

        # remove any previous build artifacts
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir)

        while time.time() <= timeout_time:
            response = self._network.get(download_artifacts_url)
            if response.status_code == http.client.OK:
                # save tar file to disk, decompress, and delete
                app.util.fs.create_dir(download_dir)
                with open(download_filepath, 'wb') as file:
                    chunk_size = 500 * 1024
                    for chunk in response.iter_content(chunk_size):
                        file.write(chunk)

                app.util.fs.extract_tar(download_filepath, delete=True)
                return

            time.sleep(1)

        raise _BuildRunnerError('Build timed out after {} seconds.'.format(timeout))

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


class _BuildRunnerError(Exception):
    """
    Raise one of these for anything that can go wrong while trying to run a build. The exception will be caught in the
    `BuildRunner.run()` method and the exception message will be logged as an error before `run()` returns.
    """
