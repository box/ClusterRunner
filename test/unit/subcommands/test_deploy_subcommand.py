import socket

from app.subcommands.deploy_subcommand import DeploySubcommand
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestDeploySubcommand(BaseUnitTestCase):
    def setUp(self):
        super().setUp()

    def test_binaries_tar_raises_exception_if_running_from_source(self):
        deploy_subcommand = DeploySubcommand()
        with self.assertRaisesRegex(SystemExit, '1'):
            deploy_subcommand._binaries_tar('python main.py deploy', '~/.clusterrunner/dist')

    def test_binaries_doesnt_raise_exception_if_running_from_bin(self):
        self.patch('os.path.isfile').return_value = True
        self.patch('app.subcommands.deploy_subcommand.compress_directory')
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._binaries_tar('clusterrunner', '~/.clusterrunner/dist')

    def test_deploy_binaries_and_conf_does_nothing_if_socket_gaierror_raised(self):
        mock_DeployTarget = self.patch('app.subcommands.deploy_subcommand.DeployTarget')
        mock_DeployTarget.side_effect = socket.gaierror()
        mock_DeployTarget_instance = mock_DeployTarget.return_value
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._deploy_binaries_and_conf(
            ['host_1'], 'invalid_host', 'username', 'exec', '/path/to/exec', '/path/to/conf')
        self.assertFalse(mock_DeployTarget_instance.deploy_binary.called)
        self.assertFalse(mock_DeployTarget_instance.deploy_conf.called)

    def test_deploy_binaries_and_conf_deploys_both_conf_and_binary_for_remote_host(self):
        mock_DeployTarget = self.patch('app.subcommands.deploy_subcommand.DeployTarget')
        mock_DeployTarget_instance = mock_DeployTarget.return_value
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._deploy_binaries_and_conf(
            ['remote_host'], 'taejun', 'username', 'exec', '/path/to/exec', '/path/to/conf')
        self.assertTrue(mock_DeployTarget_instance.deploy_binary.called)
        self.assertTrue(mock_DeployTarget_instance.deploy_conf.called)

    def test_deploy_binaries_and_conf_doesnt_deploy_conf_if_localhost_with_same_in_use_conf(self):
        self.patch('os.path.expanduser').return_value = '/home'
        mock_DeployTarget = self.patch('app.subcommands.deploy_subcommand.DeployTarget')
        mock_DeployTarget_instance = mock_DeployTarget.return_value
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._deploy_binaries_and_conf(
            ['localhost'], 'taejun', 'username', 'exec', '/path/to/exec', '/home/.clusterrunner/clusterrunner.conf')
        self.assertFalse(mock_DeployTarget_instance.deploy_conf.called)

    def test_deploy_binaries_and_conf_deploys_conf_if_localhost_with_diff_in_use_conf(self):
        self.patch('os.path.expanduser').return_value = '/home'
        mock_DeployTarget = self.patch('app.subcommands.deploy_subcommand.DeployTarget')
        mock_DeployTarget_instance = mock_DeployTarget.return_value
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._deploy_binaries_and_conf(
            ['localhost'],
            'taejun',
            'username',
            'exec',
            '/path/to/exec',
            '/home/.clusterrunner/clusterrunner_prime.conf'
        )
        self.assertTrue(mock_DeployTarget_instance.deploy_conf.called)

    def test_deploy_binaries_and_conf_deploys_binaries_if_localhost_and_different_executable_path_in_use(self):
        self.patch('os.path.expanduser').return_value = '/home'
        mock_DeployTarget = self.patch('app.subcommands.deploy_subcommand.DeployTarget')
        mock_DeployTarget_instance = mock_DeployTarget.return_value
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._deploy_binaries_and_conf(
            ['localhost'],
            'taejun',
            'username',
            '/home/.clusterrunner/dist/clusterrunner_rime',
            '/home/.clusterrunner/clusterrunner.tgz',
            '/clusterrunner.conf'
        )
        self.assertTrue(mock_DeployTarget_instance.deploy_binary.called)

    def test_deploy_binaries_and_conf_doesnt_deploy_binaries_if_localhost_and_same_executable_path_in_use(self):
        self.patch('os.path.expanduser').return_value = '/home'
        mock_DeployTarget = self.patch('app.subcommands.deploy_subcommand.DeployTarget')
        mock_DeployTarget_instance = mock_DeployTarget.return_value
        deploy_subcommand = DeploySubcommand()
        deploy_subcommand._deploy_binaries_and_conf(
            ['localhost'],
            'taejun',
            'username',
            '/home/.clusterrunner/dist/clusterrunner',
            '/home/.clusterrunner/clusterrunner.tgz',
            '/clusterrunner.conf'
        )
        self.assertFalse(mock_DeployTarget_instance.deploy_binary.called)