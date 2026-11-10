# utils/run_log.py
#
# Everything the app prints goes to SSP/logs/app.log, timestamped, and is also
# copied to the terminal while there is one.
#
# The kiosk app is often started from a terminal or over SSH (`make run | tee`).
# That terminal can go away while the app keeps running on the panel: Ctrl+C
# kills `tee` along with the app, an SSH session drops, a tab is closed. Before
# this, the next print() raised BrokenPipeError inside a Qt slot, PyQt5 turned
# that into abort(), cleanup never ran (coin acceptor left enabled), and the
# only trace was an "Aborted" dump in crash.log. Now a dead terminal is
# dropped with one note in the file, and the file keeps the full run.

import io
import os
import sys
import time

LOG_NAME = "app.log"
MAX_BYTES = 20 * 1024 * 1024  # past this at startup, the old log moves to app.log.1


class MirroredStream(io.TextIOBase):
    """A text stream that writes to a log file and, while it works, to the terminal."""

    def __init__(self, terminal, log_file, name):
        self._terminal = terminal
        self._log = log_file
        self._name = name
        self._at_line_start = True

    def _write_log(self, text):
        out = []
        for line in text.splitlines(keepends=True):
            if self._at_line_start:
                out.append(time.strftime("%Y-%m-%d %H:%M:%S "))
            out.append(line)
            self._at_line_start = line.endswith("\n")
        try:
            self._log.write("".join(out))
        except (OSError, ValueError):
            pass  # disk full or file closed at exit: the app must keep running

    def write(self, text):
        self._write_log(text)
        if self._terminal is not None:
            try:
                self._terminal.write(text)
                self._terminal.flush()
            except (OSError, ValueError) as e:
                self._terminal = None
                self._write_log(f"\n[terminal for {self._name} gone ({e.__class__.__name__}); "
                                f"logging to this file only]\n")
        return len(text)

    def flush(self):
        try:
            self._log.flush()
        except (OSError, ValueError):
            pass
        if self._terminal is not None:
            try:
                self._terminal.flush()
            except (OSError, ValueError):
                self._terminal = None

    def writable(self):
        return True

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"


def open_run_log(log_dir):
    """Open log_dir/app.log for appending, line-buffered, rotating it first if it's large."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, LOG_NAME)
    try:
        if os.path.getsize(path) > MAX_BYTES:
            os.replace(path, path + ".1")
    except OSError:
        pass
    return open(path, "a", buffering=1, encoding="utf-8", errors="replace")


def install_run_log(log_dir):
    """Route sys.stdout and sys.stderr through the run log. Returns the log file's path."""
    log_file = open_run_log(log_dir)
    log_file.write(f"\n===== start pid {os.getpid()} =====\n")
    sys.stdout = MirroredStream(sys.stdout, log_file, "stdout")
    sys.stderr = MirroredStream(sys.stderr, log_file, "stderr")
    return log_file.name
