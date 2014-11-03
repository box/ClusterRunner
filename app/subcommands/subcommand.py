from app.util import log


class Subcommand(object):

    def __init__(self):
        self._logger = log.get_logger(__name__)

    def run(self, *args, **kwargs):
        raise NotImplementedError
