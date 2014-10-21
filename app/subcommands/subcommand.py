from app.util import log


class Subcommand(object):
    thread_name = 'AppThread'

    def __init__(self):
        self._logger = log.get_logger(__name__)

    def run(self, *args, **kwargs):
        raise NotImplementedError
