from app.util.network import Network
from app.util.shell.local_shell_client import LocalShellClient
from app.util.shell.remote_shell_client import RemoteShellClient


class ShellClientFactory(object):
    @classmethod
    def create(cls, host, user):
        if Network.are_hosts_same(host, 'localhost'):
            return LocalShellClient(host, user)
        else:
            return RemoteShellClient(host, user)
