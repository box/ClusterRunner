from datetime import datetime
from threading import Lock
import requests

from app.master.build import Build
from app.master.subjob import Subjob
from app.util import analytics, log
from app.util.counter import Counter
from app.util.exceptions import ItemNotFoundError
from app.util.network import Network, RequestFailedError
from app.util.secret import Secret
from app.util.session_id import SessionId
from app.util.singleton import Singleton
from app.util.url_builder import UrlBuilder


class Slave:
    API_VERSION = 'v1'
    _slave_id_counter = Counter()

    def __init__(self, slave_url, num_executors, slave_session_id=None):
        """
        :type slave_url: str
        :type num_executors: int
        :type slave_session_id: str
        """
        self.url = slave_url
        self.num_executors = num_executors
        self.id = self._slave_id_counter.increment()
        self._num_executors_in_use = Counter()
        self._network = Network(min_connection_poolsize=num_executors)
        self.current_build_id = None
        self._last_heartbeat_time = datetime.now()
        self._is_alive = True
        self._is_in_shutdown_mode = False
        self._slave_api = UrlBuilder(slave_url, self.API_VERSION)
        self._session_id = slave_session_id
        self._logger = log.get_logger(__name__)

    def __str__(self):
        return '<slave #{} - {}>'.format(self.id, self.url)

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
        Do bookkeeping when this slave becomes idle.  Error if the slave cannot be idle.
        If the slave is in shutdown mode, clear the build_id, kill the slave, and raise an error.
        """
        if self._num_executors_in_use.value() > 0:
            raise Exception('Trying to mark slave idle while {} executors still in use.',
                            self._num_executors_in_use.value())

        self.current_build_id = None

        if self._is_in_shutdown_mode:
            self.kill()
            self._remove_slave_from_registry()
            raise SlaveMarkedForShutdownError

    def setup(self, build: Build, executor_start_index: int) -> bool:
        """
        Execute a setup command on the slave for the specified build. The setup process executes asynchronously on the
        slave and the slave will alert the master when setup is complete and it is ready to start working on subjobs.

        :param build: The build to set up this slave to work on
        :param executor_start_index: The index the slave should number its executors from for this build
        :return: Whether or not the call to start setup on the slave was successful
        """
        slave_project_type_params = build.build_request.build_parameters().copy()
        slave_project_type_params.update(build.project_type.slave_param_overrides())

        setup_url = self._slave_api.url('build', build.build_id(), 'setup')
        post_data = {
            'project_type_params': slave_project_type_params,
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
        Tell the slave to run the build teardown
        """
        if not self.is_alive():
            self._logger.notice('Teardown request to slave {} was not sent since slave is disconnected.', self.url)
            return

        teardown_url = self._slave_api.url('build', self.current_build_id, 'teardown')
        try:
            self._network.post(teardown_url)
        except (requests.ConnectionError, requests.Timeout):
            self._logger.warning('Teardown request to slave failed because slave is unresponsive.')
            self.mark_dead()

    def start_subjob(self, subjob: Subjob):
        """
        Send a subjob of a build to this slave. The slave must have already run setup for the corresponding build.
        :param subjob: The subjob to send to this slave
        """
        if not self.is_alive():
            raise DeadSlaveError('Tried to start a subjob on a dead slave.')
        if self._is_in_shutdown_mode:
            raise SlaveMarkedForShutdownError('Tried to start a subjob on a slave in shutdown mode.')

        execution_url = self._slave_api.url('build', subjob.build_id(), 'subjob', subjob.subjob_id())
        post_data = {'atomic_commands': subjob.atomic_commands()}
        try:
            response = self._network.post_with_digest(execution_url, post_data, Secret.get(), error_on_failure=True)
        except (requests.ConnectionError, requests.Timeout, RequestFailedError) as ex:
            raise SlaveCommunicationError('Call to slave service failed: {}.'.format(repr(ex))) from ex

        subjob_executor_id = response.json().get('executor_id')
        analytics.record_event(analytics.MASTER_TRIGGERED_SUBJOB, executor_id=subjob_executor_id,
                               build_id=subjob.build_id(), subjob_id=subjob.subjob_id(), slave_id=self.id)

    def num_executors_in_use(self):
        return self._num_executors_in_use.value()

    def claim_executor(self):
        new_count = self._num_executors_in_use.increment()
        if new_count > self.num_executors:
            raise Exception('Cannot claim executor on slave {}. No executors left.'.format(self.url))
        return new_count

    def free_executor(self):
        new_count = self._num_executors_in_use.decrement()
        if new_count < 0:
            raise Exception('Cannot free executor on slave {}. All are free.'.format(self.url))
        return new_count

    def is_alive(self, use_cached: bool=True) -> bool:
        """
        Is the slave API responsive?

        Note that if the slave API responds but its session id does not match the one we've stored in this
        instance, then this method will still return false.

        :param use_cached: Should we use the last returned value of the network check to the slave? If True,
            will return cached value. If False, this method will perform an actual network call to the slave.
        :return: Whether or not the slave is alive
        """
        if use_cached:
            return self._is_alive

        try:
            response = self._network.get(self._slave_api.url(), headers=self._expected_session_header())

            if not response.ok:
                self.mark_dead()
            else:
                response_data = response.json()

                if 'slave' not in response_data or 'is_alive' not in response_data['slave']:
                    self._logger.warning('{}\'s API is missing key slave[\'is_alive\'].', self.url)
                    self.mark_dead()
                elif not isinstance(response_data['slave']['is_alive'], bool):
                    self._logger.warning('{}\'s API key \'is_alive\' is not a boolean.', self.url)
                    self.mark_dead()
                else:
                    self._is_alive = response_data['slave']['is_alive']
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
        Mark this slave as being in shutdown mode.  Slaves in shutdown mode will not get new subjobs and will be
        killed and removed from slave registry when they finish teardown, or
        killed and removed from slave registry immediately if they are not processing a build.
        """
        self._is_in_shutdown_mode = True
        if self.current_build_id is None:
            self.kill()
            self._remove_slave_from_registry()

    def is_shutdown(self):
        """
        Whether the slave is in shutdown mode.
        """
        return self._is_in_shutdown_mode

    def kill(self):
        """
        Instruct the slave process to kill itself.
        """
        self._logger.notice('Killing {}', self)
        kill_url = self._slave_api.url('kill')
        try:
            self._network.post_with_digest(kill_url, {}, Secret.get())
        except (requests.ConnectionError, requests.Timeout):
            pass
        self.mark_dead()

    def mark_dead(self):
        """
        Mark the slave dead.
        """
        self._logger.warning('{} has gone offline. Last build: {}', self, self.current_build_id)
        self._is_alive = False
        self.current_build_id = None
        self._network.reset_session()  # Close any pooled connections for this slave.

    def _expected_session_header(self):
        """
        Return headers that should be sent with slave requests to verify that the master is still talking to
        the same slave service that it originally connected to.

        Note that adding these headers to existing requests may add new failure cases (e.g., slave API would
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

    def _remove_slave_from_registry(self):
        """
        Remove shutdown-ed slave from SlaveRegistry.
        """
        self._logger.info('Removing slave (url={}; id={}) from Slave Registry.'.format(self.url, self.id))
        SlaveRegistry.singleton().remove_slave(slave_url=self.url)


class SlaveRegistry(Singleton):
    """
    SlaveRegistry class is a singleton class which stores and maintains list of connected slaves.
    """

    def __init__(self):
        super().__init__()
        self._all_slaves_by_url = {}  # type: Dict[str, Slave]
        self._all_slaves_by_id = {}  # type: Dict[str, Slave]
        self._slave_dict_lock = Lock()

    def add_slave(self, slave: Slave):
        """
        Add slave in SlaveRegistry.
        """
        with self._slave_dict_lock:
            self._all_slaves_by_url[slave.url] = slave
            self._all_slaves_by_id[slave.id] = slave

    def remove_slave(self, slave: Slave=None, slave_url: str=None):
        """
        Remove slave from the both url and id dictionary.
        """
        if (slave is None) == (slave_url is None):
            raise ValueError('Only one of slave or slave_url should be specified to remove_slave().')

        with self._slave_dict_lock:
            try:
                if slave is None:
                    slave = self.get_slave(slave_url=slave_url)
                del self._all_slaves_by_url[slave.url]
                del self._all_slaves_by_id[slave.id]
            except (ItemNotFoundError, KeyError):
                # Ignore if slave does not exists in SlaveRegistry
                pass

    def get_slave(self, slave_id: int=None, slave_url: str=None) -> Slave:
        """
        Look for a slave in the registry and if not found raise "ItemNotFoundError" exception.

        :raises ItemNotFoundError when slave does not exists in Registry.
        """
        if (slave_id is None) == (slave_url is None):
            raise ValueError('Only one of slave_id or slave_url should be specified to get_slave().')

        if slave_id is not None:
            if slave_id in self._all_slaves_by_id:
                return self._all_slaves_by_id[slave_id]
        else:
            if slave_url in self._all_slaves_by_url:
                return self._all_slaves_by_url[slave_url]
        if slave_id is not None:
            error_msg = 'Requested slave (slave_id={}) does not exist.'.format(slave_id)
        else:
            error_msg = 'Requested slave (slave_url={}) does not exist.'.format(slave_url)
        raise ItemNotFoundError(error_msg)

    def get_all_slaves_by_id(self):
        return self._all_slaves_by_id

    def get_all_slaves_by_url(self):
        return self._all_slaves_by_url


class SlaveError(Exception):
    """A generic slave error occurred."""


class DeadSlaveError(SlaveError):
    """An operation was attempted on a slave which is disconnected."""


class SlaveMarkedForShutdownError(SlaveError):
    """An operation was attempted on a slave which is in shutdown mode."""


class SlaveCommunicationError(SlaveError):
    """An error occurred while communicating with the slave."""
