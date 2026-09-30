"""
Seam tests for the QR reader manager (managers/qr_reader.py): serial framing
driven through pyserial's loop:// port, and payload classification. No
physical reader, no Qt event loop.
"""
import queue

import pytest
import serial

from managers.qr_reader import QrReaderManager, classify_payload

SESSION_ID = "0123456789abcdef"


@pytest.fixture
def reader():
    """(loop port, reads queue, running manager). Bytes written to the port
    come back to the manager exactly as a reader would send them."""
    port = serial.serial_for_url("loop://", timeout=0.02)
    reads = queue.Queue()
    manager = QrReaderManager(port, reads.put)
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

    def test_unopenable_port_means_reader_off(self, monkeypatch):
        monkeypatch.setenv("QR_READER_PORT", "/dev/does-not-exist")
        assert QrReaderManager.from_config(lambda text: None) is None
