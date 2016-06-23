from queue import Queue
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
        self._builds_waiting_for_slaves = Queue()

    def get(self, build):
        """
        :type build: Build
        :rtype: BuildScheduler
        """
        with self._scheduler_creation_lock:
            scheduler = self._schedulers_by_build_id.get(build.build_id())
            if scheduler is None:
                # WIP(joey): clean up old schedulers (search through list and remove any with finished builds)
                scheduler = BuildScheduler(build, self)
                self._schedulers_by_build_id[build.build_id()] = scheduler

        return scheduler

    def next_prepared_build_scheduler(self):
        """
        Get the scheduler for the next build that has successfully completed build preparation.

        This is a blocking call--if there are no more builds that have completed build preparation and this
        method gets invoked, the execution will hang until the next build has completed build preparation.

        :rtype: BuildScheduler
        """
        build = self._builds_waiting_for_slaves.get()
        return self.get(build)

    def add_build_waiting_for_slaves(self, build):
        """
        :type build: app.master.build.Build
        """
        self._builds_waiting_for_slaves.put(build)
