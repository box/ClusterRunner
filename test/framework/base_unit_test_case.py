from contextlib import suppress
import functools
import logbook
import os
from unittest import TestCase
from unittest.mock import MagicMock, NonCallableMock, patch

from app.master.build import Build
from app.master.slave import Slave
from app.util import analytics, log
from app.util.conf.configuration import Configuration
from app.util.conf.master_config_loader import MasterConfigLoader
from app.util.counter import Counter
from app.util.unhandled_exception_handler import UnhandledExceptionHandler


class BaseUnitTestCase(TestCase):

    _base_setup_called = False
    _base_teardown_called = False
    # This allows test classes (e.g., TestNetwork) to disable network-related patches for testing the patched code.
    _do_network_mocks = True
    _fake_hostname = 'fake_hostname'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.addCleanup(self._assert_base_setup_and_teardown_were_called)

    def setUp(self):
        super().setUp()
        self.addCleanup(patch.stopall)

        self._patched_items = {}
        self._blacklist_methods_not_allowed_in_unit_tests()

        # Stub out a few library dependencies that launch subprocesses.
        self.patch('app.util.autoversioning.get_version').return_value = '0.0.0'
        self.patch('app.util.conf.base_config_loader.platform.node').return_value = self._fake_hostname

        if self._do_network_mocks:
            # requests.Session() also makes some subprocess calls on instantiation.
            self.patch('app.util.network.requests.Session')
            # Stub out Network.are_hosts_same() call with a simple string comparison.
            self.patch('app.util.network.Network.are_hosts_same', new=lambda host_a, host_b: host_a == host_b)

        # Reset singletons so that they get recreated for every test that uses them.
        Configuration.reset_singleton()
        UnhandledExceptionHandler.reset_singleton()

        # Explicitly initialize UnhandledExceptionHandler singleton here (on the main thread) since it sets up signal
        # handlers that must execute on the main thread.
        UnhandledExceptionHandler.singleton()

        MasterConfigLoader().configure_defaults(Configuration.singleton())
        MasterConfigLoader().configure_postload(Configuration.singleton())
        self.patch('app.util.conf.master_config_loader.MasterConfigLoader.load_from_config_file')

        # Reset counters
        Slave._slave_id_counter = Counter()
        Build._build_id_counter = Counter()
        analytics._event_id_generator = Counter()

        # Configure logging to go to stdout. This makes debugging easier by allowing us to see logs for failed tests.
        log.configure_logging('DEBUG')
        # Then stub out configure_logging so we don't end up logging to real files during testing.
        self.patch('app.util.log.configure_logging')

        # Set up TestHandler. This allows asserting on log messages in tests.
        self.log_handler = logbook.TestHandler(bubble=True)
        self.log_handler.push_application()

        self._base_setup_called = True

    def tearDown(self):
        super().tearDown()
        # Pop all log handlers off the stack so that we start fresh on the next test. This includes the TestHandler
        # pushed in setUp() and any handlers that may have been pushed during test execution.
        with suppress(AssertionError):  # AssertionError is raised once all handlers have been popped off the stack.
            while True:
                logbook.Handler.stack_manager.pop_application()

        self._base_teardown_called = True

    def _assert_base_setup_and_teardown_were_called(self):
        self.assertTrue(self._base_setup_called,
                        '{} must call super().setUp() in its setUp() method.'.format(self.__class__.__name__))
        self.assertTrue(self._base_teardown_called,
                        '{} must call super().tearDown() in its tearDown() method.'.format(self.__class__.__name__))

    def patch(self, target, allow_repatch=False, **kwargs):
        """
        Replaces the specified target with a mock. This is a convenience method on top of unittest.mock.patch.
        This defaults the 'autospec' parameter to True to verify that mock interfaces match the interface of the target.
        It also registers a handler to restore this patch at the end of the current test method.

        :param target: The item (object, method, etc.) to replace with a mock. (See docs for unittest.mock.patch.)
        :type target: str
        :param allow_repatch: Whether or not the specified target can be patched again -- this is most useful for
            blacklisted unit test methods: test writers must repatch any blacklisted methods in their test.
        :type allow_repatch: bool
        :param kwargs: Additional arguments to be passed to unittest.mock.patch
        :type kwargs: dict
        :return: The mock object that target has been replaced with
        :rtype: MagicMock
        """
        # Default autospec to True unless 'new' is specified (they are incompatible arguments to patch())
        if 'new' not in kwargs:
            kwargs.setdefault('autospec', True)

        patcher = patch(target, **kwargs)
        item_to_patch, _ = patcher.get_original()

        # If the item to be patched was previously patched and was repatchable, reset it so we can patch it again. Note:
        # we only allow repatching an item if that functionality is specifically requested via `allow_repatch`. This is
        # meant to protect test writers from unpredictable effects due to accidentally patching the same thing twice.
        if item_to_patch in self._patched_items:
            prev_patcher, prev_allow_repatch = self._patched_items[item_to_patch]
            if prev_allow_repatch:
                prev_patcher.stop()
                self._patched_items.pop(item_to_patch)

        # Check to see if this target has already been patched. Usually if `target` has already been patched, the
        # patcher.start() method will raise a TypeError anyway, but there are certain cases where this doesn't happen
        # reliably (e.g., 'os.unlink') so this check is an attempt to make that detection reliable.
        elif isinstance(item_to_patch, NonCallableMock):
            raise UnitTestPatchError('Target "{}" is already a mock. Has this target already been patched either in '
                                     'this class ({}) or in BaseUnitTestCase?'.format(target, self.__class__.__name__))
        try:
            mock = patcher.start()
        except TypeError as ex:
            raise UnitTestPatchError('Could not patch "{}". Has this target already been patched either in this class '
                                     '({}) or in BaseUnitTestCase?'.format(target, self.__class__.__name__)) from ex

        self._patched_items[mock] = patcher, allow_repatch
        return mock

    def patch_object(self, target, attribute, **kwargs):
        """
        Replace the named attribute on the given object with a mock.

        :type target: object
        :type attribute: str
        :rtype: MagicMock
        """
        patcher = patch.object(target, attribute, **kwargs)
        return patcher.start()

    def unpatch(self, target):
        """
        Unpatch the specified target, restoring the original method or value. This is useful when something has already
        been patched (e.g., in BaseUnitTestCase) but a specific test wants to test the code that was patched. If the
        item was not previously patched, this method raises a ValueError.

        :param target: The item to restore (object, method, etc.) that was previously patched
        :type target: str
        """
        patcher = patch(target)
        item_to_patch, _ = patcher.get_original()

        # item_to_patch should be a mock if this was already patched
        if item_to_patch in self._patched_items:
            patcher, _ = self._patched_items.pop(item_to_patch)
            patcher.stop()
        else:
            raise ValueError('Cannot unpatch target "{}" since it has not been patched!')

    def patch_abspath(self, abspath_target, cwd='/my_current_directory/'):
        """
        Replace os.path.abspath with a function that behaves similarly, but predictably. This replacement will just
        prepend the input path with the specified fake cwd.

        :param abspath_target: The target to supply to self.patch(), e.g. "module_under_test.os.path.abspath"
        :type abspath_target: str
        :param cwd: The fake current working directory that will be prepended to non-absolute input paths
        :type cwd: str
        """
        def fake_abspath(path):
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            return path

        patched_abspath = self.patch(abspath_target)
        patched_abspath.side_effect = fake_abspath
        return patched_abspath

    def trigger_graceful_app_shutdown(self):
        """
        Helper method to easily trigger graceful shutdown. The side effect of this is that all teardown handlers that
        are registered with UnhandledExceptionHandler will be executed. This method will raise a SystemExit if an
        exception is raised in any of the teardown handlers.
        """
        with UnhandledExceptionHandler.singleton():
            raise _GracefulShutdownTrigger

    def _blacklist_methods_not_allowed_in_unit_tests(self):
        """
        We maintain a list of specific methods that should never be called in unit tests for various reasons (e.g.,
        they have filesystem side effects). Methods in this list will be patched out and will actually raise an
        exception if called. This forces test writers to be conscious of what code is being exercised by their tests,
        and helps them to find the right place to mock out dependencies.

        If you encounter a UnitTestDisabledMethodError, examine the stack trace to find the appropriate place to mock.
        """
        blacklisted_methods = {
            'filesystem side effects': [
                'os.chmod', 'os.chown',  'os.fchmod', 'os.fchown', 'os.fsync', 'os.ftruncate', 'os.lchown', 'os.link',
                'os.lockf', 'os.mkdir', 'os.mkfifo', 'os.mknod', 'os.open', 'os.openpty', 'os.makedirs', 'os.remove',
                'os.rename', 'os.replace', 'os.rmdir', 'os.symlink', 'os.unlink',
                'shutil.rmtree',
                'app.util.fs.extract_tar',
                'app.util.fs.compress_directory',
                'app.util.fs.compress_directories',
                'app.util.fs.create_dir',
                'app.util.fs.write_file',
            ],
            'launching and interacting with child processes': [
                'os.execv', 'os.execve', 'os.fork', 'os.forkpty', 'os.kill', 'os.killpg', 'os.pipe', 'os.system',
                'subprocess.call',
                'subprocess.check_call',
                'subprocess.check_output',
                'subprocess.Popen.__init__',
            ],
        }
        for disabled_reason, patch_targets in blacklisted_methods.items():
            for patch_target in patch_targets:
                # Suppress UnitTestPatchError, which happens if target has already been patched (no safeguard needed).
                # Suppress AttributeError, which happens if trying to patch a target that is not available. (e.g.
                # os.chown on Windows)
                with suppress(UnitTestPatchError, AttributeError):
                    self._blackist_target(patch_target, disabled_reason)

    def _blackist_target(self, patch_target, disabled_reason):
        message = '"{}" (or the method that calls it) must be explicitly patched in this unit test to avoid {}.'.format(
            patch_target, disabled_reason)
        self.patch(patch_target, allow_repatch=True, side_effect=[UnitTestDisabledMethodError(message)])

    def no_args_side_effect(self, actual_function):
        """
        Wrap the specified function inside a new function that will swallow any args or kwargs passed in. This is
        useful in tests as a convenience method to specify side effect methods that do not accept the arguments passed
        into the original function. (A good example is replacing some method with Event.set() or Event.wait() to assist
        in testing multithreaded code.)

        :type actual_function: callable
        """
        @functools.wraps(actual_function)
        def argument_swallowing_wrapper_function(*args, **kwargs):
            return actual_function()  # do not pass args and kwargs through to actual_function
        return argument_swallowing_wrapper_function


class UnitTestDisabledMethodError(Exception):
    pass


class UnitTestPatchError(Exception):
    pass


class _GracefulShutdownTrigger(BaseException):
    """
    This is a dummy exception used only for triggering the graceful shutdown (running teardown callbacks registered
    with UnhandledExceptionHandler) during a test. This inherits from BaseException to prevent UnhandledExceptionHandler
    from raising a SystemExit.
    """
    def __init__(self):
        super().__init__('This is a fake exception to trigger graceful app shutdown.')
