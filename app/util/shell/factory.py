from app.util.shell.shell_client import ShellClient
from app.util.shell.local import LocalShellClient
from app.util.shell.remote import RemoteShellClient


class ShellClientFactory(object):
    @classmethod
    def create(cls, host, user):
        if ShellClient.is_localhost(host):
            return LocalShellClient(host, user)
        else:
            return RemoteShellClient(host, user)
