from subprocess import DEVNULL
import time

import requests

from app.util.conf.configuration import Configuration
from app.util.log import get_logger
from app.util.network import Network
from app.util.process_utils import Popen_with_delayed_expansion
from app.util.url_builder import UrlBuilder
from app.util import poll


class ServiceRunError(Exception):
    """
    An exception to represent the case where a service could not be ran
    """


class ServiceRunner(object):
    """
    An object that runs the service from the client side according to business rules.
    """

    def __init__(self, master_url, main_executable=None):
        self._master_url = master_url
        self._main_executable = main_executable or Configuration['main_executable_path']
        self._logger = get_logger(__name__)

    def run_master(self):
        """
        Runs the master service if it is not running
        :return:
        """
        self._logger.info('Running master on {}'.format(self._master_url))
        if self.is_master_up():
            return
        cmd = [self._main_executable, 'master', '--port', self._port(self._master_url)]

        self._run_service(cmd, self._master_url)

    def _port(self, service_url):
        """
        :param service_url: the url to get the port from
        :type service_url: string - in the form of host:port
        :rtype: string
        :return: the port
        """
        return service_url.split(':')[-1]

    def run_slave(self, port=None):
        """
        Runs the slave if it is not running
        :type port: int | None
        :return:
        """
        self._logger.info('Running slave')
        cmd = [self._main_executable, 'slave', '--master-url', self._master_url]
        if port is not None:
            cmd.extend(['--port', str(port)])

        self._run_service(cmd)

    def block_until_build_queue_empty(self, timeout=60):
        """
        This blocks until the master's build queue is empty. This data is exposed via the /queue endpoint and contains
        any jobs that are currently building or not yet started. If the queue is not empty before the timeout, this
        method raises an exception.

        :param timeout: The maximum number of seconds to block before raising an exception.
        :type timeout: int
        """
        master_api = UrlBuilder(self._master_url)
        queue_url = master_api.url('queue')

        def is_queue_empty():
            queue_resp = requests.get(queue_url)
            if queue_resp and queue_resp.ok:
                queue_data = queue_resp.json()
                if 'queue' in queue_data and len(queue_data['queue']) == 0:
                    return True
            return False

        if not poll.wait_for(is_queue_empty, timeout, 0.5):
            raise Exception('Master service did not become idle before timeout.')

    def kill(self):
        self._run_service([self._main_executable, 'stop'])

    def _run_service(self, cmd, service_url=None):
        """
        Runs a service with a specified shell cmd
        :param service_url:
        :param cmd: shell command for running the service as a background process
        :return:
        """
        print('running cmd: {}'.format(cmd))
        if service_url is not None and self.is_up(service_url):
            return
        Popen_with_delayed_expansion(cmd, stdout=DEVNULL)
        if service_url is not None and not self.is_up(service_url, timeout=10):
            raise ServiceRunError("Failed to run service on {}.".format(service_url))

    def is_master_up(self):
        """
        Checks if the master is up
        :rtype: bool
        """
        return self.is_up(self._master_url)

    def is_up(self, service_url, timeout=0.1):
        """
        Checks if the service is up
        :type service_url: string
        :type timeout: float
        :rtype: bool
        """
        network = Network()
        timeout_time = time.time() + timeout
        while True:
            try:
                resp = network.get('http://{}'.format(service_url), timeout=timeout)
                if resp and resp.ok:
                    return True
            except (requests.RequestException, ConnectionError):
                pass
            if time.time() > timeout_time:
                break
            time.sleep(0.5)

        return False
