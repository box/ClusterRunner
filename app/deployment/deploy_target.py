import os

from app.util.shell.factory import ShellClientFactory


class DeployTarget(object):
    """
    A "deploy target" is the host to which clusterrunner will be deployed to. Deployment entails putting
    in place the clusterrunner binaries and configuration only. This class is not responsible for manipulating
    processes and stopping/starting services.
    """

    def __init__(self, host, username):
        """
        :param host: the fully qualified hostname of the host to deploy to
        :type host: str
        :param username: the user who is executing this process and whose ssh credentials will be used
        :type username: str
        """
        self._host = host
        self._username = username
        self._shell_client = ShellClientFactory.create(host, username)

    def deploy_binary(self, source_tar, dest_dir):
        """
        Given the tarred/zipped binary directory on the current host, move to the self.host and unzip
        it into the dest_dir on the remote host. This method will create the directory if it doesn't exist,
        and will overwrite the directory if it already exists.

        :param source_tar: the path the tar-zipped clusterrunner binary is on the current host
        :type source_tar: str
        :param dest_dir: the path to place the clusterrunner binaries on the deploy target host
        :type dest_dir: str
        """
        parent_dest_dir = os.path.dirname(dest_dir)
        self._shell_client.exec_command('rm -rf {0}; mkdir -p {0}'.format(dest_dir), error_on_failure=True)
        self._shell_client.copy(source_tar, '{}/clusterrunner.tgz'.format(parent_dest_dir))
        self._shell_client.exec_command(
            command='tar zxvf {}/clusterrunner.tgz -C {}'.format(parent_dest_dir, dest_dir),
            error_on_failure=True
        )

    def deploy_conf(self, source_path, dest_path):
        """
        Given a conf file on the local host, send it to the remote deploy target host, and set the
        proper permissions.

        :param source_path: the path to the clusterrunner conf file on the current host
        :type source_path: str
        :param dest_path: the path to place the clusterrunner conf file on the deploy target host
        :type dest_path: str
        """
        if not os.path.exists(source_path):
            raise RuntimeError('Expected configuration file to exist in {}, but does not.'.format(source_path))

        self._shell_client.copy(source_path, dest_path)
        # Must set permissions of conf to '600' for security purposes.
        self._shell_client.exec_command('chmod 600 {}'.format(dest_path), error_on_failure=True)
