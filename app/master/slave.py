from app.util import analytics, log
from app.util.counter import Counter
from app.util.network import Network
from app.util.safe_thread import SafeThread
from app.util.secret import Secret
from app.util.url_builder import UrlBuilder
import requests.exceptions


class Slave(object):

    API_VERSION = 'v1'
    _slave_id_counter = Counter()

    def __init__(self, slave_url, num_executors):
        """
        :type slave_url: str
        :type num_executors: int
        """
        self.url = slave_url
        self.num_executors = num_executors
        self.id = self._slave_id_counter.increment()
        self._num_executors_in_use = Counter()
        self._network = Network(min_connection_poolsize=num_executors)
        self.current_build_id = None
        self._is_alive = True
        self._slave_api = UrlBuilder(slave_url, self.API_VERSION)
        self._logger = log.get_logger(__name__)

    def api_representation(self):
        return {
            'url': self.url,
            'id': self.id,
            'num_executors': self.num_executors,
            'num_executors_in_use': self.num_executors_in_use(),
            'current_build_id': self.current_build_id,
            'is_alive': self.is_alive(),
        }

    def mark_as_idle(self):
        """
        Do bookkeeping when this slave becomes idle.  Error if the slave cannot be idle.
        """
        if self._num_executors_in_use.value() != 0:
            raise Exception('Trying to mark slave idle while {} executors still in use.',
                            self._num_executors_in_use.value())

        self.current_build_id = None

    def setup(self, build):
        """
        Execute a setup command on the slave for the specified build. The setup process executes asynchronously on the
        slave and the slave will alert the master when setup is complete and it is ready to start working on subjobs.

        :param build: The build to set up this slave to work on
        :type build: Build
        """
        slave_project_type_params = build.build_request.build_parameters().copy()
        slave_project_type_params.update(build.project_type.slave_param_overrides())

        setup_url = self._slave_api.url('build', build.build_id(), 'setup')
        post_data = {
            'project_type_params': slave_project_type_params,
            'build_executor_start_index': build.num_executors_allocated,
        }
        self._network.post_with_digest(setup_url, post_data, Secret.get())
        self.current_build_id = build.build_id()

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
            raise RuntimeError('Tried to start a subjob on a dead slave! ({}, id: {})'.format(self.url, self.id))

        SafeThread(target=self._async_start_subjob, args=(subjob,)).start()

    def _async_start_subjob(self, subjob):
        """
        :type subjob: Subjob
        """
        execution_url = self._slave_api.url('build', subjob.build_id(), 'subjob', subjob.subjob_id())
        post_data = {
            'subjob_artifact_dir': subjob.artifact_dir(),
            'atomic_commands': subjob.atomic_commands(),
        }
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

        :param use_cached: Should we use the last returned value of the network check to the slave? If True,
            will return cached value. If False, this method will perform an actual network call to the slave.
        :type use_cached: bool
        :rtype: bool
        """
        if use_cached:
            return self._is_alive

        try:
            response = self._network.get(self._slave_api.url())

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
