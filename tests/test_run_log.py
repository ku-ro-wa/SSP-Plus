"""
The app's output goes to SSP/logs/app.log as well as the terminal (utils/run_log.py),
and a terminal that goes away must not take the app down.

On the kiosk, Ctrl+C on `make run | tee` killed tee first; the SIGINT handler's
print() then raised BrokenPipeError inside Qt, PyQt5 aborted, and cleanup never
ran (coin acceptor left enabled).
"""
import os
import re
import subprocess
import sys
import textwrap

from utils.run_log import MAX_BYTES, MirroredStream, open_run_log

STAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} "
RUN_LOG_MODULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SSP", "utils", "run_log.py")


class DeadTerminal:
    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


class LiveTerminal:
    def __init__(self):
        self.text = ""

    def write(self, text):
        self.text += text

    def flush(self):
        pass


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_lines_go_to_the_terminal_and_the_file_with_timestamps(tmp_path):
    log = open_run_log(str(tmp_path))
    terminal = LiveTerminal()
    stream = MirroredStream(terminal, log, "stdout")
    print("first", file=stream)
    stream.write("partial ")
    stream.write("line\nsecond\n")

    assert terminal.text == "first\npartial line\nsecond\n"
    lines = _read(log.name).splitlines()
    assert [re.sub(STAMP, "", line) for line in lines] == ["first", "partial line", "second"]
    assert all(re.match(STAMP, line) for line in lines)


def test_a_dead_terminal_is_dropped_and_the_file_keeps_everything(tmp_path):
    log = open_run_log(str(tmp_path))
    stream = MirroredStream(DeadTerminal(), log, "stdout")

    print("SIGINT received, shutting down", file=stream)  # raised BrokenPipeError before
    stream.flush()
    print("cleanup completed", file=stream)

    text = _read(log.name)
    assert "SIGINT received" in text and "cleanup completed" in text
    assert text.count("terminal for stdout gone (BrokenPipeError)") == 1


def test_a_large_log_is_rotated_at_startup(tmp_path):
    path = tmp_path / "app.log"
    path.write_bytes(b"x" * (MAX_BYTES + 1))
    log = open_run_log(str(tmp_path))
    log.write("new run\n")
    log.close()
    assert (tmp_path / "app.log.1").stat().st_size == MAX_BYTES + 1
    assert path.read_text() == "new run\n"


def test_printing_after_the_reading_end_of_a_pipe_closes_does_not_raise(tmp_path):
    """The real failure: stdout is a pipe to tee, tee exits, the app prints."""
    code = textwrap.dedent(f"""
        import importlib.util, os, sys
        spec = importlib.util.spec_from_file_location("run_log", {RUN_LOG_MODULE!r})
        run_log = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_log)
        run_log.install_run_log({str(tmp_path)!r})
        sys.stdin.read()          # wait until the reader has gone
        for _ in range(3):
            print("after tee died")
        sys.__stderr__.write("survived\\n")
    """)
    child = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child.stdout.close()          # the reader (tee) is gone
    _, err = child.communicate("", timeout=20)

    assert child.returncode == 0, err
    assert "survived" in err
    text = _read(tmp_path / "app.log")
    assert text.count("after tee died") == 3
    assert "terminal for stdout gone (BrokenPipeError)" in text
