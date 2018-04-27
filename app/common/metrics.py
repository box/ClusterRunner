from enum import Enum

from typing import Callable, Iterator, List

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.core import GaugeMetricFamily


http_request_duration_seconds = Histogram(  # pylint: disable=no-value-for-parameter
    'http_request_duration_seconds',
    'Latency of HTTP requests in seconds',
    ['method', 'endpoint', 'status'],
    buckets=(.005, .01, .05, .1, .25, .5, 1.0, 2.5, 5.0, 7.5, 10.0, 20.0, 50.0, float('inf')))

build_state_duration_seconds = Histogram(  # pylint: disable=no-value-for-parameter
    'build_state_duration_seconds',
    'Total amount of time a build spends in each build state',
    ['state'])

serialized_build_time_seconds = Histogram(  # pylint: disable=no-value-for-parameter
    'serialized_build_time_seconds',
    'Total amount of time that would have been consumed by builds if all work was done serially')

internal_errors = Counter(
    'internal_errors',
    'Total number of internal errors',
    ['type'])


class ErrorType(str, Enum):
    AtomizerFailure = 'AtomizerFailure'
    NetworkRequestFailure = 'NetworkRequestFailure'
    PostBuildFailure = 'PostBuildFailure'
    SubjobStartFailure = 'SubjobStartFailure'
    SubjobWriteFailure = 'SubjobWriteFailure'
    ZipFileCreationFailure = 'ZipFileCreationFailure'

    def __str__(self):
        """
        Even though this class inherits from str, still include a __str__ method so that
        metrics in the /metrics endpoint appear as
        internal_errors{type="PostBuildFailure"} 1.0
        instead of
        internal_errors{type="ErrorType.PostBuildFailure"} 1.0
        """
        return self.value


class WorkersCollector:
    """
    Prometheus collector to collect the total number of alive/dead/idle workers connected to the manager.
    collect() is called once each time prometheus scrapes the /metrics endpoint. This class ensures that
    1. The list of workers only gets iterated through once per scrape
    2. A single worker is is not double counted in 2 states
    """

    _workers_collector_is_registered = False

    def __init__(self, get_workers: Callable[[], List['app.manager.worker.Worker']]):
        self._get_workers = get_workers

    def collect(self) -> Iterator[GaugeMetricFamily]:
        active, idle, dead = 0, 0, 0
        for worker in self._get_workers():
            if worker.is_alive(use_cached=True) and worker.current_build_id is not None:
                active += 1
            elif worker.is_alive(use_cached=True) and worker.current_build_id is None:
                idle += 1
            elif not worker.is_alive(use_cached=True) and not worker.is_shutdown():
                # Worker is not alive and was not deliberately put in shutdown mode. Count it as dead.
                dead += 1
            else:
                # If not worker.is_alive() and worker.is_shutdown() = True then we have deliberately
                # and gracefully killed the worker. We do not want to categorize such a worker as 'dead'
                pass

        workers_gauge = GaugeMetricFamily('workers', 'Total number of workers', labels=['state'])
        workers_gauge.add_metric(['active'], active)
        workers_gauge.add_metric(['idle'], idle)
        workers_gauge.add_metric(['dead'], dead)
        yield workers_gauge

    @classmethod
    def register_workers_metrics_collector(cls, get_workers: Callable[[], List['app.manager.worker.Worker']]):
        if not cls._workers_collector_is_registered:
            REGISTRY.register(WorkersCollector(get_workers))
            cls._workers_collector_is_registered = True
