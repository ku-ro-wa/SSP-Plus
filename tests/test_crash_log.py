"""
crash.log brackets each run with markers (utils/crash_log.py).

faulthandler's dumps carry no time or pid, so on their own they can't say
which run crashed or whether the app was still running. A "started" line
goes before the run and main() writes "event loop ended" when app.exec_()
returns, so a dump below that line happened after the app closed.
These tests segfault real child processes and read the file they leave.
"""
import os
import re
import subprocess
import sys
import textwrap

import pytest

import utils.crash_log as crash_log

MODULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SSP", "utils", "crash_log.py")
MARKER = re.compile(r"^--- pid (\d+) (started|event loop ended) \d{4}-\d\d-\d\d \d\d:\d\d:\d\d ---$")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="segfaults a child process")


def _run_child(log_dir, body):
    """Run body in a child that has enabled the crash log; returns (pid, returncode, log lines)."""
    code = textwrap.dedent(f"""
        import importlib.util, os, atexit, faulthandler
        spec = importlib.util.spec_from_file_location("crash_log", {MODULE!r})
        crash_log = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(crash_log)
        print(os.getpid(), flush=True)
        crash_log.enable_crash_log({str(log_dir)!r})
    """) + textwrap.dedent(body)
    child = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    pid = int(child.stdout.split()[0])
    with open(os.path.join(log_dir, "crash.log"), encoding="utf-8") as f:
        return pid, child.returncode, f.read().splitlines()


def _markers(lines):
    return [(int(m.group(1)), m.group(2)) for m in map(MARKER.match, lines) if m]


def test_a_crash_while_running_has_only_the_started_marker_above_it(tmp_path):
    pid, code, lines = _run_child(tmp_path, "faulthandler._sigsegv()\n")

    assert code != 0
    assert _markers(lines) == [(pid, "started")]
    assert lines[0].startswith(f"--- pid {pid} started")
    assert any("Segmentation fault" in line for line in lines[1:])


def test_a_crash_after_the_event_loop_ended_comes_below_that_marker(tmp_path):
    # The atexit hook stands in for Python's teardown after main() returns.
    pid, code, lines = _run_child(tmp_path, """
        atexit.register(faulthandler._sigsegv)
        crash_log.mark_crash_log("event loop ended")
    """)

    assert code != 0
    assert _markers(lines) == [(pid, "started"), (pid, "event loop ended")]
    ended = next(i for i, line in enumerate(lines) if "event loop ended" in line)
    crash = next(i for i, line in enumerate(lines) if "Segmentation fault" in line)
    assert crash > ended


def test_a_clean_run_leaves_just_its_two_markers_and_runs_append(tmp_path):
    first, code1, _ = _run_child(tmp_path, 'crash_log.mark_crash_log("event loop ended")\n')
    second, code2, lines = _run_child(tmp_path, 'crash_log.mark_crash_log("event loop ended")\n')

    assert (code1, code2) == (0, 0)
    assert lines == [line for line in lines if MARKER.match(line)]
    assert _markers(lines) == [(first, "started"), (first, "event loop ended"),
                               (second, "started"), (second, "event loop ended")]


def test_marking_never_raises_without_a_usable_file(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_log, "_crash_file", None)
    crash_log.mark_crash_log("event loop ended")  # not enabled: nothing to write

    closed = open(tmp_path / "crash.log", "a", encoding="utf-8")
    closed.close()
    monkeypatch.setattr(crash_log, "_crash_file", closed)
    crash_log.mark_crash_log("event loop ended")  # file closed at exit: swallowed
