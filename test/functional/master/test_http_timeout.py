from collections import deque
import os
import tempfile
from threading import Event, Thread
import yaml

from genty import genty, genty_dataset
from tornado import httpserver, ioloop, web

from test.framework.functional.base_functional_test_case import BaseFunctionalTestCase
from test.functional.job_configs import JOB_WITH_SETUP_AND_TEARDOWN


@genty
class TestHttpTimeout(BaseFunctionalTestCase):

    UNRESPONSIVE_SLAVE_PORT = 43001
    NORMAL_SLAVE_PORT = 43002

    @genty_dataset(
        on_first_request=([],),
        on_second_request=(['{"slave": {"is_alive": true}}'],),
    )
    def test_unresponsive_slave_does_not_hang_master(self, responses):
        # Start the master and an unresponsive slave.
        master = self.cluster.start_master(default_http_timeout=1)
        unresponsive_slave = UnresponsiveServer().start(
            port=self.UNRESPONSIVE_SLAVE_PORT,
            responses=deque(responses))
        unresponsive_slave_id = master.connect_slave(
            'http://localhost:{}'.format(self.UNRESPONSIVE_SLAVE_PORT),
            num_executors=1)

        self.addCleanup(unresponsive_slave.stop)

        # Start a build which will be cause an attempt to allocate the unresponsive slave.
        project_dir = tempfile.TemporaryDirectory()
        build_resp = master.post_new_build({
            'type': 'directory',
            'config': yaml.safe_load(JOB_WITH_SETUP_AND_TEARDOWN.config[os.name])['JobWithSetupAndTeardown'],
            'project_directory': project_dir.name,
        })
        build_id = build_resp['build_id']

        self.assertTrue(master.block_until_slave_offline(unresponsive_slave_id, timeout=10),
                        'Unresponsive slave should be marked offline.')

        # First slave should now be marked offline. Connect a real slave to finish the build.
        self.cluster.start_slaves(num_slaves=1, start_port=self.NORMAL_SLAVE_PORT)
        self.assertTrue(master.block_until_build_finished(build_id, timeout=30),
                        'The build should finish building within the timeout.')
        self.assert_build_has_successful_status(build_id)


class UnresponsiveServer:
    """
    Server to emulate an unresponsive slave. This can optionally can return a sequence of
    specified responses before finally becoming unresponsive.
    """
    def __init__(self):
        self._server_started_event = Event()
        self._stop_hanging_event = Event()
        self._server_thread = None
        self._server = None
        self._ioloop = None

    def start(self, port: int, responses: deque=None) -> 'UnresponsiveServer':
        """
        Start the server on a separate thread. Block until the server is started.
        :param port: Port to serve on
        :param responses: A list of responses to return before becoming unresponsive
        """
        self._server_thread = Thread(
            target=self._run_server,
            name='UnresponsiveServer',
            kwargs={'port': port, 'responses': responses},
        )
        self._server_thread.start()
        self._server_started_event.wait()
        return self

    def _run_server(self, port: int, responses: deque=None):
        self._server = httpserver.HTTPServer(web.Application([
            (r'.*', UnresponsiveHandler, {
                'stop_hanging_event': self._stop_hanging_event,
                'responses': responses,
            })
        ]))
        self._server.listen(port)
        self._ioloop = ioloop.IOLoop.current()
        self._ioloop.add_callback(self._server_started_event.set)
        self._ioloop.start()  # blocks until ioloop is stopped

    def stop(self):
        """Stop the running server. Block until the server is stopped."""
        if self._server_thread:
            self._server.stop()
            self._ioloop.add_callback(self._ioloop.stop)
            self._stop_hanging_event.set()  # Unblock any currently hanging request.
            self._server_thread.join()  # Make sure server dies before returning.


class UnresponsiveHandler(web.RequestHandler):
    def initialize(self, stop_hanging_event: Event=None, responses: deque=None):
        self._responses = responses
        self._stop_hanging_event = stop_hanging_event

    def _handle_request(self):
        if self._responses:
            self.write(self._responses.popleft())
        else:
            self._stop_hanging_event.wait(300)  # Block request without responding.

    # Use same handler for all http methods.
    get = _handle_request
    post = _handle_request
    put = _handle_request
