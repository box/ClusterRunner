from app.util import analytics, log
from app.util.counter import Counter
from app.util.network import Network
from app.util.safe_thread import SafeThread
from app.util.secret import Secret
from app.util.url_builder import UrlBuilder
from app.util import util


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
        self.is_alive = True
        self._slave_api = UrlBuilder(slave_url, self.API_VERSION)
        self._logger = log.get_logger(__name__)

    def api_representation(self):
        return {
            'url': self.url,
            'id': self.id,
            'num_executors': self.num_executors,
            'num_executors_in_use': self.num_executors_in_use(),
            'current_build_id': self.current_build_id,
        }

    def mark_as_idle(self):
        """
        Do bookkeeping when this slave becomes idle.  Error if the slave cannot be idle.
        """
        if self._num_executors_in_use.value() != 0:
            raise Exception('Trying to mark slave idle while {} executors still in use.',
                            self._num_executors_in_use.value())

        self.current_build_id = None

    def setup(self, build_id, project_type_params):
        """
        Execute a setup command on the slave for the specified build. The command is executed asynchronously from the
        perspective of this method, but any subjobs will block until the slave finishes executing the setup command.

        :param build_id: The build id that this setup command is for.
        :type build_id: int

        :param project_type_params: The parameters that define the project type this build will execute in
        :type project_type_params: dict
        """
        setup_url = self._slave_api.url('build', build_id, 'setup')
        slave_project_type_params = util.project_type_params_for_slave(project_type_params)
        post_data = {
            'project_type_params': slave_project_type_params,
        }
        self._network.post_with_digest(setup_url, post_data, Secret.get())
        self.current_build_id = build_id

    def teardown(self):
        """
        Tell the slave to run the build teardown
        """
        if self.is_alive:
            teardown_url = self._slave_api.url('build', self.current_build_id, 'teardown')
            self._network.post(teardown_url)
        else:
            self._logger.notice('Teardown request to slave {} was not sent since slave is disconnected.', self.url)

    def start_subjob(self, subjob):
        """
        :type subjob: Subjob
        """
        if not self.is_alive:
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
