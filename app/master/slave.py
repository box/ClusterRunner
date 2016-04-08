import requests.exceptions

from app.util import analytics, log
from app.util.counter import Counter
from app.util.network import Network
from app.util.safe_thread import SafeThread
from app.util.secret import Secret
from app.util.session_id import SessionId
from app.util.url_builder import UrlBuilder


class Slave(object):

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
        if self._num_executors_in_use.value() != 0:
            raise Exception('Trying to mark slave idle while {} executors still in use.',
                            self._num_executors_in_use.value())

        self.current_build_id = None

        if self._is_in_shutdown_mode:
            self.kill()
            raise SlaveMarkedForShutdownError

    def setup(self, build, executor_start_index):
        """
        Execute a setup command on the slave for the specified build. The setup process executes asynchronously on the
        slave and the slave will alert the master when setup is complete and it is ready to start working on subjobs.

        :param build: The build to set up this slave to work on
        :type build: Build
        :param executor_start_index: The index the slave should number its executors from for this build
        :type executor_start_index: int
        """
        slave_project_type_params = build.build_request.build_parameters().copy()
        slave_project_type_params.update(build.project_type.slave_param_overrides())

        setup_url = self._slave_api.url('build', build.build_id(), 'setup')
        post_data = {
            'project_type_params': slave_project_type_params,
            'build_executor_start_index': executor_start_index,
        }

        self.current_build_id = build.build_id()
        self._network.post_with_digest(setup_url, post_data, Secret.get())

    def teardown(self):
        """
        Tell the slave to run the build teardown
        """
        if self.is_alive():
            teardown_url = self._slave_api.url('build', self.current_build_id, 'teardown')
            self._network.post(teardown_url)
        else:
            self._logger.notice('Teardown request to slave {} was not sent since slave is disconnected.', self.url)

    def start_subjob(self, subjob):
        """
        :type subjob: Subjob
        """
        if not self.is_alive():
            raise DeadSlaveError('Tried to start a subjob on a dead slave! ({}, id: {})'.format(self.url, self.id))

        if self._is_in_shutdown_mode:
            raise SlaveMarkedForShutdownError('Tried to start a subjob on a slave in shutdown mode. ({}, id: {})'
                                              .format(self.url, self.id))

        SafeThread(target=self._async_start_subjob, args=(subjob,)).start()

    def _async_start_subjob(self, subjob):
        """
        :type subjob: Subjob
        """
        execution_url = self._slave_api.url('build', subjob.build_id(), 'subjob', subjob.subjob_id())
        post_data = {'atomic_commands': subjob.atomic_commands()}
        response = self._network.post_with_digest(execution_url, post_data, Secret.get(), error_on_failure=True)

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

    def is_alive(self, use_cached=True):
        """
        Is the slave API responsive?

        Note that if the slave API responds but its session id does not match the one we've stored in this
        instance, then this method will still return false.

        :param use_cached: Should we use the last returned value of the network check to the slave? If True,
            will return cached value. If False, this method will perform an actual network call to the slave.
        :type use_cached: bool
        :rtype: bool
        """
        if use_cached:
            return self._is_alive

        try:
            response = self._network.get(self._slave_api.url(), headers=self._expected_session_header())

            if not response.ok:
                self._is_alive = False
            else:
                response_data = response.json()

                if 'slave' not in response_data or 'is_alive' not in response_data['slave']:
                    self._logger.warning('{}\'s API is missing key slave[\'is_alive\'].', self.url)
                    self._is_alive = False
                elif not isinstance(response_data['slave']['is_alive'], bool):
                    self._logger.warning('{}\'s API key \'is_alive\' is not a boolean.', self.url)
                    self._is_alive = False
                else:
                    self._is_alive = response_data['slave']['is_alive']
        except requests.exceptions.ConnectionError:
            self._logger.warning('Slave with url {} is offline.', self.url)
            self._is_alive = False

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
        killed when they finish teardown, or killed immediately if they are not processing a build.
        """
        self._is_in_shutdown_mode = True
        if self.current_build_id is None:
            self.kill()

    def is_shutdown(self):
        """
        Whether the slave is in shutdown mode.
        """
        return self._is_in_shutdown_mode

    def kill(self):
        """
        Instructs the slave process to kill itself.
        """
        kill_url = self._slave_api.url('kill')
        self._network.post_with_digest(kill_url, {}, Secret.get())
        self.mark_dead()

    def mark_dead(self):
        """
        Marks the slave dead.
        """
        self.set_is_alive(False)
        self.current_build_id = None

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


class DeadSlaveError(Exception):
    """
    Tried an operation on a slave which is disconnected.
    """


class SlaveMarkedForShutdownError(Exception):
    """
    Tried an operation which could have added additional work to a slave which is in shutdown mode.
    """
