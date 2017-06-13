from prometheus_client import Histogram


request_latency = Histogram(  # pylint: disable=no-value-for-parameter
    'request_latency_seconds',
    'Latency of HTTP requests in seconds')

build_state_duration_seconds = Histogram(  # pylint: disable=no-value-for-parameter
    'build_state_duration_seconds',
    'Total amount of time a build spends in each build state',
    ['state'])
