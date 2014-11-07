from app.util.network import Network
from app.util.shell.local import LocalShellClient
from app.util.shell.remote import RemoteShellClient


class ShellClientFactory(object):
    @classmethod
    def create(cls, host, user):
        if Network.are_hosts_same(host, 'localhost'):
            return LocalShellClient(host, user)
        else:
            return RemoteShellClient(host, user)
