from unittest.mock import Mock, MagicMock

from app.master.atom import Atom, AtomState
from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.slave import DeadSlaveError, SlaveMarkedForShutdownError, Slave
from app.master.subjob import Subjob
from app.util.secret import Secret
from app.util.session_id import SessionId
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestSlave(BaseUnitTestCase):

    _FAKE_SLAVE_URL = 'splinter.sensei.net:43001'
    _FAKE_NUM_EXECUTORS = 10

    def setUp(self):
        super().setUp()
        self.mock_network = self.patch('app.master.slave.Network').return_value

    def test_disconnect_command_is_sent_during_teardown_when_slave_is_still_connected(self):
        slave = self._create_slave()
        slave.current_build_id = 3
        slave._is_alive = True

        slave.teardown()

        expected_teardown_url = 'http://splinter.sensei.net:43001/v1/build/3/teardown'
        self.mock_network.post.assert_called_once_with(expected_teardown_url)

    def test_disconnect_command_is_not_sent_during_teardown_when_slave_has_disconnected(self):
        slave = self._create_slave()
        slave.current_build_id = 3
        slave._is_alive = False

        slave.teardown()

        self.assertEqual(self.mock_network.post.call_count, 0,
                         'Master should not send teardown command to slave when slave has disconnected.')

    def test_git_project_params_are_modified_for_slave(self):
        slave = self._create_slave()
        slave._network.post_with_digest = Mock()

        build_request = BuildRequest({
            'type': 'git',
            'url': 'http://original-user-specified-url',
        })
        mock_git = Mock(slave_param_overrides=Mock(return_value={
            'url': 'ssh://new-url-for-clusterrunner-master',
            'extra': 'something_extra',
        }))
        mock_build = MagicMock(spec=Build, build_request=build_request,
                               build_id=Mock(return_value=888), project_type=mock_git)

        slave.setup(mock_build, executor_start_index=777)

        slave._network.post_with_digest.assert_called_with(
            'http://{}/v1/build/888/setup'.format(self._FAKE_SLAVE_URL),
            {
                'build_executor_start_index': 777,
                'project_type_params': {
                    'type': 'git',
                    'url': 'ssh://new-url-for-clusterrunner-master',
                    'extra': 'something_extra'}
            },
            Secret.get()
        )

    def test_build_id_is_set_on_master_before_telling_slave_to_setup(self):
        # This test enforces an ordering that avoids a race where the slave finishes setup and posts back before the
        # master has actually set the slave's current_build_id.
        slave = self._create_slave()
        mock_build = Mock()

        def assert_slave_build_id_is_already_set(*args, **kwargs):
            self.assertEqual(slave.current_build_id, mock_build.build_id(),
                             'slave.current_build_id should be set before the master tells the slave to do setup.')

        slave._network.post_with_digest = Mock(side_effect=assert_slave_build_id_is_already_set)
        slave.setup(mock_build, executor_start_index=0)

        self.assertEqual(slave._network.post_with_digest.call_count, 1,
                         'The behavior that this test is checking depends on slave setup being triggered via '
                         'slave._network.post_with_digest().')

    def test_is_alive_returns_cached_value_if_use_cache_is_true(self):
        slave = self._create_slave()
        slave._is_alive = False
        is_slave_alive = slave.is_alive(use_cached=True)

        self.assertFalse(is_slave_alive)
        self.assertFalse(self.mock_network.get.called)

    def test_is_alive_returns_false_if_response_not_ok(self):
        slave = self._create_slave()
        response_mock = self.mock_network.get.return_value
        response_mock.ok = False
        is_slave_alive = slave.is_alive(use_cached=False)

        self.assertFalse(is_slave_alive)
        self.assertFalse(response_mock.json.called)

    def test_is_alive_returns_false_if_response_is_ok_but_is_alive_is_false(self):
        slave = self._create_slave()
        response_mock = self.mock_network.get.return_value
        response_mock.ok = True
        response_mock.json.return_value = {'slave': {'is_alive': False}}
        is_slave_alive = slave.is_alive(use_cached=False)

        self.assertFalse(is_slave_alive)

    def test_is_alive_returns_true_if_response_is_ok_and_is_alive_is_true(self):
        slave = self._create_slave()
        response_mock = self.mock_network.get.return_value
        response_mock.ok = True
        response_mock.json.return_value = {'slave': {'is_alive': True}}
        is_slave_alive = slave.is_alive(use_cached=False)

        self.assertTrue(is_slave_alive)

    def test_is_alive_makes_correct_network_call_to_slave(self):
        slave = self._create_slave(
            slave_url='fake.slave.gov:43001',
            slave_session_id='abc-123')

        slave.is_alive(use_cached=False)

        self.mock_network.get.assert_called_once_with(
            'http://fake.slave.gov:43001/v1',
            headers={SessionId.EXPECTED_SESSION_HEADER_KEY: 'abc-123'})

    def test_mark_as_idle_raises_when_executors_are_in_use(self):
        slave = self._create_slave()
        slave._num_executors_in_use.increment()

        self.assertRaises(Exception, slave.mark_as_idle)

    def test_mark_as_idle_raises_when_slave_is_in_shutdown_mode(self):
        slave = self._create_slave()
        slave._is_in_shutdown_mode = True
        slave.kill = Mock()

        self.assertRaises(SlaveMarkedForShutdownError, slave.mark_as_idle)
        slave.kill.assert_called_once_with()

    def test_start_subjob_raises_if_slave_is_dead(self):
        slave = self._create_slave()
        slave._is_alive = False

        self.assertRaises(DeadSlaveError, slave.start_subjob, Mock())

    def test_start_subjob_raises_if_slave_is_shutdown(self):
        slave = self._create_slave()
        slave._is_in_shutdown_mode = True

        self.assertRaises(SlaveMarkedForShutdownError, slave.start_subjob, Mock())

    def test_set_shutdown_mode_should_set_is_shutdown_and_not_kill_slave_if_slave_has_a_build(self):
        slave = self._create_slave()
        slave.current_build_id = 1
        slave.kill = Mock()

        slave.set_shutdown_mode()

        self.assertTrue(slave._is_in_shutdown_mode)
        assert not slave.kill.called

    def test_set_shutdown_mode_should_kill_slave_if_slave_has_no_build(self):
        slave = self._create_slave()
        slave.kill = Mock()

        slave.set_shutdown_mode()

        slave.kill.assert_called_once_with()

    def test_kill_should_post_to_slave_api(self):
        slave = self._create_slave()
        slave._network.post_with_digest = Mock()

        slave.kill()

        assert slave._network.post_with_digest.called

    def _create_slave(self, **kwargs):
        """
        Create a slave for testing.
        :param kwargs: Any constructor parameters for the slave; if none are specified, test defaults will be used.
        :rtype: Slave
        """
        kwargs.setdefault('slave_url', self._FAKE_SLAVE_URL)
        kwargs.setdefault('num_executors', self._FAKE_NUM_EXECUTORS)
        return Slave(**kwargs)
