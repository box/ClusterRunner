from threading import Lock

from app.master.build_scheduler import BuildScheduler


class BuildSchedulerPool(object):
    """
    A BuildSchedulerPool creates and manages a group of BuildScheduler instances.
    Since there is a one-to-one relationship between Build and BuildScheduler, this
    class exists to make it easier to create and manage scheduler instances.
    """
    def __init__(self):
        self._schedulers_by_build_id = {}
        self._scheduler_creation_lock = Lock()

    def get(self, build):
        """
        :type build: Build
        :rtype: BuildScheduler
        """
        with self._scheduler_creation_lock:
            scheduler = self._schedulers_by_build_id.get(build.build_id())
            if scheduler is None:
                # WIP(joey): clean up old schedulers (search through list and remove any with finished builds)
                scheduler = BuildScheduler(build)
                self._schedulers_by_build_id[build.build_id()] = scheduler

        return scheduler
