from datetime import datetime
from threading import Lock
import requests

from app.manager.build import Build
from app.manager.subjob import Subjob
from app.util import analytics, log
from app.util.counter import Counter
from app.util.exceptions import ItemNotFoundError
from app.util.network import Network, RequestFailedError
from app.util.secret import Secret
from app.util.session_id import SessionId
from app.util.singleton import Singleton
from app.util.url_builder import UrlBuilder


class Worker:
    API_VERSION = 'v1'
    _worker_id_counter = Counter()

    def __init__(self, worker_url, num_executors, worker_session_id=None):
        """
        :type worker_url: str
        :type num_executors: int
        :type worker_session_id: str
        """
        self.url = worker_url
        self.num_executors = num_executors
        self.id = self._worker_id_counter.increment()
        self._num_executors_in_use = Counter()
        self._network = Network(min_connection_poolsize=num_executors)
        self.current_build_id = None
        self._last_heartbeat_time = datetime.now()
        self._is_alive = True
        self._is_in_shutdown_mode = False
        self._worker_api = UrlBuilder(worker_url, self.API_VERSION)
        self._session_id = worker_session_id
        self._logger = log.get_logger(__name__)

    def __str__(self):
        return '<worker #{} - {}>'.format(self.id, self.url)

    def api_representation(self):
        return {
            'url': self.url,
            'id': self.id,
            'session_id': self._session_id,
            'num_executors': self.num_executors,
            'num_executors_in_use': self.num_executors_in_use(),
            'current_build_id': self.current_build_id,
            'is_alive': self.is_alive(),
            'is_in_shutdown_mode': self._is_in_shutdown_mode,
        }

    def mark_as_idle(self):
        """
        Do bookkeeping when this worker becomes idle.  Error if the worker cannot be idle.
        If the worker is in shutdown mode, clear the build_id, kill the worker, and raise an error.
        """
        if self._num_executors_in_use.value() != 0:
            raise Exception('Trying to mark worker idle while {} executors still in use.',
                            self._num_executors_in_use.value())

        self.current_build_id = None

        if self._is_in_shutdown_mode:
            self.kill()
            self._remove_worker_from_registry()
            raise WorkerMarkedForShutdownError

    def setup(self, build: Build, executor_start_index: int) -> bool:
        """
        Execute a setup command on the worker for the specified build. The setup process executes asynchronously on the
        worker and the worker will alert the manager when setup is complete and it is ready to start working on subjobs.

        :param build: The build to set up this worker to work on
        :param executor_start_index: The index the worker should number its executors from for this build
        :return: Whether or not the call to start setup on the worker was successful
        """
        worker_project_type_params = build.build_request.build_parameters().copy()
        worker_project_type_params.update(build.project_type.worker_param_overrides())

        setup_url = self._worker_api.url('build', build.build_id(), 'setup')
        post_data = {
            'project_type_params': worker_project_type_params,
            'build_executor_start_index': executor_start_index,
        }

        self.current_build_id = build.build_id()
        try:
            self._network.post_with_digest(setup_url, post_data, Secret.get())
        except (requests.ConnectionError, requests.Timeout) as ex:
            self._logger.warning('Setup call to {} failed with {}: {}.', self, ex.__class__.__name__, str(ex))
            self.mark_dead()
            return False
        return True

    def teardown(self):
        """
        Tell the worker to run the build teardown
        """
        if not self.is_alive():
            self._logger.notice('Teardown request to worker {} was not sent since worker is disconnected.', self.url)
            return

        teardown_url = self._worker_api.url('build', self.current_build_id, 'teardown')
        try:
            self._network.post(teardown_url)
        except (requests.ConnectionError, requests.Timeout):
            self._logger.warning('Teardown request to worker failed because worker is unresponsive.')
            self.mark_dead()

    def start_subjob(self, subjob: Subjob):
        """
        Send a subjob of a build to this worker. The worker must have already run setup for the corresponding build.
        :param subjob: The subjob to send to this worker
        """
        if not self.is_alive():
            raise DeadWorkerError('Tried to start a subjob on a dead worker.')
        if self._is_in_shutdown_mode:
            raise WorkerMarkedForShutdownError('Tried to start a subjob on a worker in shutdown mode.')

        execution_url = self._worker_api.url('build', subjob.build_id(), 'subjob', subjob.subjob_id())
        post_data = {'atomic_commands': subjob.atomic_commands()}
        try:
            response = self._network.post_with_digest(execution_url, post_data, Secret.get(), error_on_failure=True)
        except (requests.ConnectionError, requests.Timeout, RequestFailedError) as ex:
            raise WorkerCommunicationError('Call to worker service failed: {}.'.format(repr(ex))) from ex

        subjob_executor_id = response.json().get('executor_id')
        analytics.record_event(analytics.MASTER_TRIGGERED_SUBJOB, executor_id=subjob_executor_id,
                               build_id=subjob.build_id(), subjob_id=subjob.subjob_id(), worker_id=self.id)

    def num_executors_in_use(self):
        return self._num_executors_in_use.value()

    def claim_executor(self):
        new_count = self._num_executors_in_use.increment()
        if new_count > self.num_executors:
            raise Exception('Cannot claim executor on worker {}. No executors left.'.format(self.url))
        return new_count

    def free_executor(self):
        new_count = self._num_executors_in_use.decrement()
        if new_count < 0:
            raise Exception('Cannot free executor on worker {}. All are free.'.format(self.url))
        return new_count

    def is_alive(self, use_cached: bool=True) -> bool:
        """
        Is the worker API responsive?

        Note that if the worker API responds but its session id does not match the one we've stored in this
        instance, then this method will still return false.

        :param use_cached: Should we use the last returned value of the network check to the worker? If True,
            will return cached value. If False, this method will perform an actual network call to the worker.
        :return: Whether or not the worker is alive
        """
        if use_cached:
            return self._is_alive

        try:
            response = self._network.get(self._worker_api.url(), headers=self._expected_session_header())

            if not response.ok:
                self.mark_dead()
            else:
                response_data = response.json()

                if 'worker' not in response_data or 'is_alive' not in response_data['worker']:
                    self._logger.warning('{}\'s API is missing key worker[\'is_alive\'].', self.url)
                    self.mark_dead()
                elif not isinstance(response_data['worker']['is_alive'], bool):
                    self._logger.warning('{}\'s API key \'is_alive\' is not a boolean.', self.url)
                    self.mark_dead()
                else:
                    self._is_alive = response_data['worker']['is_alive']
        except (requests.ConnectionError, requests.Timeout):
            self.mark_dead()

        return self._is_alive

    def set_is_alive(self, value):
        """
        Setter for the self._is_alive attribute.

        :type value: bool
        """
        self._is_alive = value

    def set_shutdown_mode(self):
        """
        Mark this worker as being in shutdown mode.  Workers in shutdown mode will not get new subjobs and will be
        killed and removed from worker registry when they finish teardown, or
        killed and removed from worker registry immediately if they are not processing a build.
        """
        self._is_in_shutdown_mode = True
        if self.current_build_id is None:
            self.kill()
            self._remove_worker_from_registry()

    def is_shutdown(self):
        """
        Whether the worker is in shutdown mode.
        """
        return self._is_in_shutdown_mode

    def kill(self):
        """
        Instruct the worker process to kill itself.
        """
        self._logger.notice('Killing {}', self)
        kill_url = self._worker_api.url('kill')
        try:
            self._network.post_with_digest(kill_url, {}, Secret.get())
        except (requests.ConnectionError, requests.Timeout):
            pass
        self.mark_dead()

    def mark_dead(self):
        """
        Mark the worker dead.
        """
        self._logger.warning('{} has gone offline. Last build: {}', self, self.current_build_id)
        self._is_alive = False
        self.current_build_id = None
        self._network.reset_session()  # Close any pooled connections for this worker.

    def _expected_session_header(self):
        """
        Return headers that should be sent with worker requests to verify that the manager is still talking to
        the same worker service that it originally connected to.

        Note that adding these headers to existing requests may add new failure cases (e.g., worker API would
        start returning a 412) so we should make sure all potential 412 errors are handled appropriately when
        adding these headers to existing requests.

        :rtype: dict
        """
        headers = {}
        if self._session_id:
            headers[SessionId.EXPECTED_SESSION_HEADER_KEY] = self._session_id

        return headers

    def update_last_heartbeat_time(self):
        self._last_heartbeat_time = datetime.now()

    def get_last_heartbeat_time(self) -> datetime:
        return self._last_heartbeat_time

    def _remove_worker_from_registry(self):
        """
        Remove shutdown-ed worker from WorkerRegistry.
        """
        self._logger.info('Removing worker (url={}; id={}) from Worker Registry.'.format(self.url, self.id))
        WorkerRegistry.singleton().remove_worker(worker_url=self.url)


class WorkerRegistry(Singleton):
    """
    WorkerRegistry class is a singleton class which stores and maintains list of connected workers.
    """

    def __init__(self):
        super().__init__()
        self._all_workers_by_url = {}  # type: Dict[str, Worker]
        self._all_workers_by_id = {}  # type: Dict[str, Worker]
        self._worker_dict_lock = Lock()

    def add_worker(self, worker: Worker):
        """
        Add worker in WorkerRegistry.
        """
        with self._worker_dict_lock:
            self._all_workers_by_url[worker.url] = worker
            self._all_workers_by_id[worker.id] = worker

    def remove_worker(self, worker: Worker=None, worker_url: str=None):
        """
        Remove worker from the both url and id dictionary.
        """
        if (worker is None) == (worker_url is None):
            raise ValueError('Only one of worker or worker_url should be specified to remove_worker().')

        with self._worker_dict_lock:
            try:
                if worker is None:
                    worker = self.get_worker(worker_url=worker_url)
                del self._all_workers_by_url[worker.url]
                del self._all_workers_by_id[worker.id]
            except (ItemNotFoundError, KeyError):
                # Ignore if worker does not exists in WorkerRegistry
                pass

    def get_worker(self, worker_id: int=None, worker_url: str=None) -> Worker:
        """
        Look for a worker in the registry and if not found raise "ItemNotFoundError" exception.

        :raises ItemNotFoundError when worker does not exists in Registry.
        """
        if (worker_id is None) == (worker_url is None):
            raise ValueError('Only one of worker_id or worker_url should be specified to get_worker().')

        if worker_id is not None:
            if worker_id in self._all_workers_by_id:
                return self._all_workers_by_id[worker_id]
        else:
            if worker_url in self._all_workers_by_url:
                return self._all_workers_by_url[worker_url]
        if worker_id is not None:
            error_msg = 'Requested worker (worker_id={}) does not exist.'.format(worker_id)
        else:
            error_msg = 'Requested worker (worker_url={}) does not exist.'.format(worker_url)
        raise ItemNotFoundError(error_msg)

    def get_all_workers_by_id(self):
        return self._all_workers_by_id

    def get_all_workers_by_url(self):
        return self._all_workers_by_url


class WorkerError(Exception):
    """A generic worker error occurred."""


class DeadWorkerError(WorkerError):
    """An operation was attempted on a worker which is disconnected."""


class WorkerMarkedForShutdownError(WorkerError):
    """An operation was attempted on a worker which is in shutdown mode."""


class WorkerCommunicationError(WorkerError):
    """An error occurred while communicating with the worker."""
