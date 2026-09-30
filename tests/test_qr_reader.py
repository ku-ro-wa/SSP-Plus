"""
Seam tests for the QR reader manager (managers/qr_reader.py): serial framing
driven through pyserial's loop:// port, and payload classification. No
physical reader, no Qt event loop.
"""
import queue
import threading

import pytest
import serial

from managers.qr_reader import (CONNECTED, UNAVAILABLE, QrReaderManager, classify_payload,
                                describe_reader_status, should_log_status_change)

SESSION_ID = "0123456789abcdef"


@pytest.fixture
def reader():
    """(loop port, reads queue, running manager). Bytes written to the port
    come back to the manager exactly as a reader would send them."""
    port = serial.serial_for_url("loop://", timeout=0.02)
    reads = queue.Queue()
    manager = QrReaderManager(lambda: port, reads.put)
    manager.start()
    yield port, reads
    manager.stop()
    port.close()


def _next(reads):
    return reads.get(timeout=2)


class TestFraming:
    def test_cr_terminates_a_read(self, reader):
        port, reads = reader
        port.write(f"{SESSION_ID}:123456\r".encode())
        assert _next(reads) == f"{SESSION_ID}:123456"

    def test_stray_lf_is_stripped(self, reader):
        port, reads = reader
        port.write(f"{SESSION_ID}:123456\r\n".encode())
        port.write(b"V1:ABC\n\r")
        assert _next(reads) == f"{SESSION_ID}:123456"
        assert _next(reads) == "V1:ABC"

    def test_line_split_across_two_writes(self, reader):
        port, reads = reader
        port.write(f"{SESSION_ID}:12".encode())
        assert reads.empty()
        port.write(b"3456\r")
        assert _next(reads) == f"{SESSION_ID}:123456"

    def test_one_signal_per_read(self, reader):
        port, reads = reader
        port.write(b"aaa\rbbb\r")
        assert [_next(reads), _next(reads)] == ["aaa", "bbb"]

    def test_empty_lines_are_not_reads(self, reader):
        port, reads = reader
        port.write(b"\r\r\n\rxyz\r")
        assert _next(reads) == "xyz"

    def test_undecodable_bytes_still_emit_a_read(self, reader):
        port, reads = reader
        port.write(b"\xff\xfe\r")
        assert isinstance(_next(reads), str)


class TestClassification:
    def test_session_payload(self):
        read = classify_payload(f"{SESSION_ID}:123456")
        assert read.kind == "session"
        assert (read.session_id, read.otp) == (SESSION_ID, "123456")

    def test_voucher_payload(self):
        assert classify_payload("V1:ABCDEF").kind == "voucher"

    @pytest.mark.parametrize("text", [
        "",
        "hello",
        f"{SESSION_ID}:12345",          # 5 digits
        f"{SESSION_ID}:1234567",        # 7 digits
        f"{SESSION_ID}:12345a",         # non-digit OTP
        f"{SESSION_ID.upper()}:123456",  # uppercase hex
        f"{SESSION_ID[:-1]}:123456",    # 15 hex chars
        f"{SESSION_ID}g:123456",        # non-hex
        f" {SESSION_ID}:123456",        # stray whitespace
        f"{SESSION_ID}:123456 ",
        f"{SESSION_ID}:123456\n",       # $ would let a trailing newline through
        f"{SESSION_ID}:١٢٣٤٥٦",          # non-ASCII digits
        "v1:ABCDEF",                   # prefix is case-sensitive
    ])
    def test_malformed(self, text):
        assert classify_payload(text).kind == "malformed"


class TestFromConfig:
    @pytest.mark.parametrize("value", ["", "   "])
    def test_blank_port_means_reader_off(self, monkeypatch, value):
        monkeypatch.setenv("QR_READER_PORT", value)
        assert QrReaderManager.from_config(lambda text: None) is None

    def test_unopenable_port_still_returns_a_retrying_manager(self, monkeypatch):
        monkeypatch.setenv("QR_READER_PORT", "/dev/does-not-exist")
        manager = QrReaderManager.from_config(lambda text: None)
        assert manager is not None
        assert manager.status is None  # nothing tried until start()


class FakePort:
    """A port whose reads fail once `unplug()` is called, like a pulled USB cable."""

    in_waiting = 0

    def __init__(self, data=b""):
        self._chunks = queue.Queue()
        if data:
            self._chunks.put(data)
        self._unplugged = threading.Event()
        self.closed = False

    def unplug(self):
        self._unplugged.set()

    def read(self, size=1):
        if self._unplugged.is_set():
            raise serial.SerialException("device disappeared")
        try:
            return self._chunks.get(timeout=0.02)
        except queue.Empty:
            return b""

    def close(self):
        self.closed = True


class TestReaderAvailability:
    """Reader loss and recovery, driven with a scripted port factory."""

    @pytest.fixture
    def harness(self):
        class Harness:
            def __init__(self):
                self.reads = queue.Queue()
                self.changes = queue.Queue()
                self.opens = []      # every port handed out (or the failure raised)
                self.plan = []       # next open() outcomes: a FakePort or an Exception
                self.manager = None

            def open(self):
                outcome = self.plan.pop(0) if self.plan else OSError("no reader")
                self.opens.append(outcome)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            def start(self):
                self.manager = QrReaderManager(
                    self.open, self.reads.put,
                    on_status=lambda new, old, detail="": self.changes.put((new, old)),
                    retry_seconds=0.02)
                self.manager.start()
                return self.manager

        h = Harness()
        yield h
        if h.manager is not None:
            h.manager.stop()

    def test_port_that_fails_to_open_reports_unavailable_once_across_retries(self, harness):
        harness.plan = [OSError("nope")] * 3
        harness.start()
        assert harness.changes.get(timeout=2) == (UNAVAILABLE, None)
        # Wait for at least three more open attempts
        for _ in range(100):
            if len(harness.opens) >= 4:
                break
            threading.Event().wait(0.02)
        assert len(harness.opens) >= 4
        assert harness.changes.empty()
        assert harness.manager.status == UNAVAILABLE

    def test_reader_that_appears_later_is_connected_and_reads_resume(self, harness):
        harness.plan = [OSError("nope"), FakePort(b"abc\r")]
        harness.start()
        assert harness.changes.get(timeout=2) == (UNAVAILABLE, None)
        assert harness.changes.get(timeout=2) == (CONNECTED, UNAVAILABLE)
        assert harness.reads.get(timeout=2) == "abc"

    def test_port_disappearing_mid_run_reports_unavailable_then_recovers(self, harness):
        first, second = FakePort(b"one\r"), FakePort(b"two\r")
        harness.plan = [first, second]
        harness.start()
        assert harness.changes.get(timeout=2) == (CONNECTED, None)
        assert harness.reads.get(timeout=2) == "one"

        first.unplug()
        assert harness.changes.get(timeout=2) == (UNAVAILABLE, CONNECTED)
        assert first.closed
        assert harness.changes.get(timeout=2) == (CONNECTED, UNAVAILABLE)
        assert harness.reads.get(timeout=2) == "two"
        assert harness.changes.empty()

    def test_port_that_opens_but_cannot_be_read_never_reports_connected(self, harness):
        stale = [FakePort() for _ in range(3)]
        for port in stale:
            port.unplug()
        harness.plan = list(stale)
        harness.start()
        assert harness.changes.get(timeout=2) == (UNAVAILABLE, None)
        for _ in range(100):
            if len(harness.opens) >= 3:
                break
            threading.Event().wait(0.02)
        assert harness.changes.empty()

    def test_partial_line_from_before_the_loss_is_discarded(self, harness):
        first, second = FakePort(b"12"), FakePort(b"3\r")
        harness.plan = [first, second]
        harness.start()
        assert harness.changes.get(timeout=2) == (CONNECTED, None)
        first.unplug()
        assert harness.changes.get(timeout=2) == (UNAVAILABLE, CONNECTED)
        assert harness.reads.get(timeout=2) == "3"

    def test_stop_while_unavailable_returns_promptly(self, harness):
        harness.start()
        assert harness.changes.get(timeout=2) == (UNAVAILABLE, None)
        harness.manager.retry_seconds = 60
        harness.manager.stop()


class TestStatusPresentation:
    def test_no_manager_means_not_configured_not_an_error(self):
        assert describe_reader_status(None) == "Not configured"

    @pytest.mark.parametrize("status, text", [
        (CONNECTED, "Connected"),
        (UNAVAILABLE, "Not connected"),
        (None, "Starting"),
    ])
    def test_status_text(self, status, text):
        class Stub:
            pass
        stub = Stub()
        stub.status = status
        assert describe_reader_status(stub) == text

    @pytest.mark.parametrize("new, old, logged", [
        (UNAVAILABLE, None, True),        # never opened at startup
        (UNAVAILABLE, CONNECTED, True),   # lost
        (CONNECTED, UNAVAILABLE, True),   # recovered
        (CONNECTED, None, False),         # normal startup is not an error
    ])
    def test_which_changes_reach_the_error_log(self, new, old, logged):
        assert should_log_status_change(new, old) is logged
