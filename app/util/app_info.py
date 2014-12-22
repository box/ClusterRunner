import sys
import threading
import traceback


def get_app_info_string():
    """
    Get a string representing global information about the application. This is used for debugging.

    :rtype: str
    """
    app_info_list = _get_formatted_thread_stack_traces()
    return '\n'.join(app_info_list)


def _get_formatted_thread_stack_traces():
    """
    Get the formatted stack trace string for each currently running thread.

    :rtype: list[str]
    """
    formatted_traces = []
    threads_by_id = {thread.ident: thread for thread in threading.enumerate()}

    # The sys_current_frames() method is intended to be used for debugging like this.
    for thread_id, stack in sys._current_frames().items():  # pylint: disable=protected-access
        thread = threads_by_id.get(thread_id)
        if thread:
            thread_type = 'daemon' if thread.isDaemon() else 'nondaemon'
            thread_stack_trace = ''.join(traceback.format_stack(stack))
            formatted_traces.append('Current trace for {} thread "{}":\n{}'
                                    .format(thread_type, thread.name, thread_stack_trace))

    return formatted_traces
