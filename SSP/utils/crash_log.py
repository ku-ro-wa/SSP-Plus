# utils/crash_log.py
#
# Native crashes (segfault, abort) leave no Python traceback, so faulthandler
# writes every thread's stack to SSP/logs/crash.log. Its dumps carry no time
# and no pid, and the file is shared by every run, so on their own they can't
# say which run crashed, when, or whether the app was still working or had
# already closed. Two marker lines around each run answer that:
#
#   --- pid 1234 started 2026-11-06 20:36:40 ---
#   --- pid 1234 event loop ended 2026-11-06 20:37:41 ---
#
# main() writes the second as soon as app.exec_() returns, after cleanup() has
# run and before Python tears down what's left (modules, Qt objects, exit
# hooks). A dump below a run's "event loop ended" line happened after the app
# had closed; one below only its "started" line happened while it was running.
# The pid matches app.log's "===== start pid N =====".

import faulthandler
import os
import time

CRASH_LOG_NAME = "crash.log"

_crash_file = None  # kept open for the life of the process; faulthandler writes to its fd


def mark_crash_log(event):
    """Append '--- pid N <event> <time> ---' to crash.log. Never raises."""
    if _crash_file is None:
        return
    try:
        _crash_file.write(f"--- pid {os.getpid()} {event} {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        _crash_file.flush()
    except (OSError, ValueError):
        pass  # a log line must never stop the app or its shutdown


def enable_crash_log(log_dir):
    """Send native-crash stacks to log_dir/crash.log, after a 'started' marker.

    Returns the file's path. Raises OSError if it can't be opened.
    """
    global _crash_file
    os.makedirs(log_dir, exist_ok=True)
    _crash_file = open(os.path.join(log_dir, CRASH_LOG_NAME), "a", encoding="utf-8")
    mark_crash_log("started")
    faulthandler.enable(file=_crash_file, all_threads=True)
    return _crash_file.name
