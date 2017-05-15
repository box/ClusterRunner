from prometheus_client import Histogram


request_latency = Histogram(  # pylint: disable=no-value-for-parameter
    'request_latency_seconds',
    'Latency of HTTP requests in seconds')
