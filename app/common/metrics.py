from enum import Enum

from typing import Callable, Iterator, List

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.core import GaugeMetricFamily


http_request_duration_seconds = Histogram(  # pylint: disable=no-value-for-parameter
    'http_request_duration_seconds',
    'Latency of HTTP requests in seconds',
    ['method', 'endpoint', 'status'])

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
    SetupBuildFailure = 'SetupBuildFailure'
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


class SlavesCollector:
    """
    Prometheus collector to collect the total number of alive/dead/idle slaves connected to the master.
    collect() is called once each time prometheus scrapes the /metrics endpoint. This class ensures that
    1. The list of slaves only gets iterated through once per scrape
    2. A single slave is is not double counted in 2 states
    """

    _slaves_collector_is_registered = False

    def __init__(self, get_slaves: Callable[[], List['app.master.slave.Slave']]):
        self._get_slaves = get_slaves

    def collect(self) -> Iterator[GaugeMetricFamily]:
        active, idle, dead = 0, 0, 0
        for slave in self._get_slaves():
            if not slave.is_alive(use_cached=True):
                dead += 1
            elif slave.current_build_id is not None:
                active += 1
            else:
                idle += 1

        slaves_gauge = GaugeMetricFamily('slaves', 'Total number of slaves', labels=['state'])
        slaves_gauge.add_metric(['active'], active)
        slaves_gauge.add_metric(['idle'], idle)
        slaves_gauge.add_metric(['dead'], dead)
        yield slaves_gauge

    @classmethod
    def register_slaves_metrics_collector(cls, get_slaves: Callable[[], List['app.master.slave.Slave']]):
        if not cls._slaves_collector_is_registered:
            REGISTRY.register(SlavesCollector(get_slaves))
            cls._slaves_collector_is_registered = True
