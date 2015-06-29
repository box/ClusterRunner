from app.util import fs
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestFs(BaseUnitTestCase):

    def test_async_delete_calls_correct_commands(self):
        popen_mock = self.patch('app.util.fs.Popen_with_delayed_expansion')
        move_mock = self.patch('shutil.move')
        self.patch('os.path.isdir').return_value = True
        mkdtemp_mock = self.patch('tempfile.mkdtemp')
        mkdtemp_mock.return_value = '/tmp/dir'
        fs.async_delete('/some/dir')

        move_mock.assert_called_with('/some/dir', '/tmp/dir')
        popen_mock.assert_called_with(['rm', '-rf', '/tmp/dir'])