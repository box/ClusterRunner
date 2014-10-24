from collections import defaultdict
import logbook
from logbook import Logger, NullHandler, RotatingFileHandler, StreamHandler
import logbook.compat
import logging
import os
import sys
from termcolor import colored

from app.util.conf.configuration import Configuration
from app.util.fs import create_dir


# This custom format string takes care of setting field widths to make logs more aligned and readable.
_LOG_FORMAT_STRING = (
    '[{record.time!s:.23}] '             # 23 chars of date and time (omits last 3 digits of microseconds)
    '{record.level_name:7} '             # log level - min field width = 7
    '{record.thread_name:15.15} '        # thread name - min and max field width = 15
    '{record.channel:15.15} '            # module name - min and max field width = 15
    '{record.message}'
)

# When logging to the console, just print the message
_SIMPLIFIED_LOG_FORMAT_STRING = '{record.message}'

_LOG_COLORS = defaultdict(lambda: ('grey', []), {  # default to grey
    logbook.CRITICAL: ('magenta', ['bold']),
    logbook.ERROR: ('red', ['bold']),
    logbook.WARNING: ('yellow', ['bold']),
    logbook.NOTICE: ('yellow', []),
    logbook.INFO: ('cyan', []),
    logbook.DEBUG: ('green', []),
})

_SIMPLIFIED_LOG_COLORS = defaultdict(lambda: (None, []), {
    logbook.CRITICAL: ('magenta', ['bold']),
    logbook.ERROR: ('red', ['bold']),
    logbook.WARNING: ('yellow', ['bold']),
})


def get_logger(logger_name=None):
    """
    The common pattern for using this method is to create a logger instance in your class constructor:
      >>> self._logger = get_logger(__name__)

    Then use that logger instance anywhere you'd place a print statement. Provide extra arguments directly to the
    logger method instead of using string.format:
      >>> self._logger.warning('The file {} was not found.', filename)

    Do not use print() in the app code -- we should be using a logger instead.
        - This gives us much more granular and semantic control over what the system is outputting (via the log level).
        - It ensures multiple threads will not be writing to stdout at the same time.
        - The work of doing string formatting is only done if the message is actually going to be output.

    :param logger_name: The name of the logger -- in most cases this just should be the module name (__name__)
    :type logger_name: str
    :return: The logger instance
    :rtype: logbook.Logger
    """
    name_without_package = logger_name.rsplit('.', 1)[-1]  # e.g., converts "project_type.docker" to "docker"
    return Logger(name_without_package)


def configure_logging(log_level=None, log_file=None, simplified_console_logs=False):
    """
    This should be called once as early as possible in app startup to configure logging handlers and formatting.

    :param log_level: The level at which to record log messages (DEBUG|INFO|NOTICE|WARNING|ERROR|CRITICAL)
    :type log_level: str
    :param log_file: The file to write logs to, or None to disable logging to a file
    :type log_file: str | None
    :param simplified_console_logs: Whether or not to use the simplified logging format and coloring
    :type simplified_console_logs: bool
    """
    # Set datetimes in log messages to be local timezone instead of UTC
    logbook.set_datetime_format('local')

    # Redirect standard lib logging to capture third-party logs in our log files (e.g., tornado, requests)
    logging.root.setLevel(logging.WARNING)  # don't include DEBUG/INFO/NOTICE-level logs from third parties
    logbook.compat.redirect_logging(set_root_logger_level=False)

    # Add a NullHandler to suppress all log messages lower than our desired log_level. (Otherwise they go to stderr.)
    NullHandler().push_application()

    log_level = log_level or Configuration['log_level']
    format_string, log_colors = _LOG_FORMAT_STRING, _LOG_COLORS
    if simplified_console_logs:
        format_string, log_colors = _SIMPLIFIED_LOG_FORMAT_STRING, _SIMPLIFIED_LOG_COLORS

    # handler for stdout
    log_handler = _ColorizingStreamHandler(
        stream=sys.stdout,
        level=log_level,
        format_string=format_string,
        log_colors=log_colors,
        bubble=True,
    )
    log_handler.push_application()

    # handler for log file
    if log_file:
        create_dir(os.path.dirname(log_file))
        previous_log_file_exists = os.path.exists(log_file)

        event_handler = _ColorizingRotatingFileHandler(
            filename=log_file,
            level=log_level,
            format_string=_LOG_FORMAT_STRING,
            log_colors=_LOG_COLORS,
            bubble=True,
            max_size=Configuration['max_log_file_size'],
            backup_count=Configuration['max_log_file_backups'],
        )
        if previous_log_file_exists:
            event_handler.perform_rollover()  # force starting a new log file on application startup

        event_handler.push_application()


class _ColorizingStreamHandler(StreamHandler):
    """
    This is a StreamHandler that colorizes its log messages.
    """
    def __init__(self, log_colors, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log_colors = log_colors

    def format_and_encode(self, record):
        output = super().format_and_encode(record)
        color, attrs = self._log_colors[record.level]
        return colored(output, color, attrs=attrs) if color else output


class _ColorizingRotatingFileHandler(_ColorizingStreamHandler, RotatingFileHandler):
    """
    This is a RotatingFileHandler that colorizes its log messages.
    """
