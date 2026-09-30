# managers/qr_reader.py
#
# The kiosk's QR reader (see CONTEXT.md and ADR 0004): a cheap embedded 2D
# module run as a USB serial port. Not the flatbed document scanner — that's
# managers/scanner.py.
#
# Three pieces, all free of Qt so they can be tested without an event loop:
#   - QrReaderManager: background thread that frames the serial stream into
#     CR-terminated reads and hands each one to a callback.
#   - classify_payload(): every read is untrusted (anyone can reconfigure the
#     reader), so it's checked against exact formats before anything acts on it.
#   - decide_redemption(): classified read + current screen + SessionManager
#     -> what the app should do.

import re
import threading
import time
from dataclasses import dataclass

from config import get_config

try:
    import serial
except ImportError:  # pyserial is optional unless a reader port is configured
    serial = None

READER_BAUDRATE = 9600  # ignored by a USB CDC port, but pyserial wants one
_POLL_TIMEOUT_SECONDS = 0.1
_JOIN_TIMEOUT_SECONDS = 2.0

# fullmatch + [0-9]/[0-9a-f] (not \d or $) so a trailing newline, whitespace,
# uppercase hex or non-ASCII digits are all malformed.
_SESSION_PAYLOAD = re.compile(r"([0-9a-f]{16}):([0-9]{6})")
_VOUCHER_PREFIX = "V1:"

# Screens that accept a read (and can show a message about it). Every other
# screen ignores reads silently.
_REDEEMABLE_SCREENS = {"idle", "homepage", "wifi", "email"}
_KIOSK_SOURCES = {"wifi", "email"}

DUPLICATE_WINDOW_SECONDS = 3.0

MSG_CANT_READ = "Couldn't read that, type your code."
MSG_CANT_USE_HERE = "This code can't be used here."
MSG_VOUCHER_AT_PAYMENT = "Vouchers can only be used at payment."
# Same wording a typed code gets for a session that is gone or already used.
MSG_NOT_FOUND_OR_USED = "Incorrect or expired code"


@dataclass
class QrRead:
    kind: str  # 'session' | 'voucher' | 'malformed'
    session_id: str = None
    otp: str = None


@dataclass
class RedemptionOutcome:
    action: str  # 'open_files' | 'rejected' (show `message`) | 'ignore' (silent)
    source: str = None
    files: list = None
    message: str = None


def classify_payload(text: str) -> QrRead:
    match = _SESSION_PAYLOAD.fullmatch(text)
    if match:
        return QrRead("session", session_id=match.group(1), otp=match.group(2))
    if text.startswith(_VOUCHER_PREFIX):
        return QrRead("voucher")
    return QrRead("malformed")


def decide_redemption(read: QrRead, screen: str, session_manager) -> RedemptionOutcome:
    """Decide what a read means on `screen`. Only a well-formed Session payload
    on an accepting screen can touch the Session Manager; malformed reads,
    Voucher payloads and wrong-Source Sessions never count as a failed attempt."""
    if screen not in _REDEEMABLE_SCREENS:
        return RedemptionOutcome("ignore")
    if read.kind == "voucher":
        return RedemptionOutcome("rejected", message=MSG_VOUCHER_AT_PAYMENT)
    if read.kind != "session":
        return RedemptionOutcome("rejected", message=MSG_CANT_READ)

    # Checked before verification so a wrong-source Session never gets an attempt counted.
    source = session_manager.get_session_source(read.session_id)
    if source is None:
        return RedemptionOutcome("rejected", message=MSG_NOT_FOUND_OR_USED)
    if source not in _KIOSK_SOURCES:
        return RedemptionOutcome("rejected", message=MSG_CANT_USE_HERE)
    # A typed code never resolves a used Session, so a read must not reopen its files.
    if session_manager.get_session_status(read.session_id) == "verified":
        return RedemptionOutcome("rejected", message=MSG_NOT_FOUND_OR_USED)

    success, message, files = session_manager.verify_otp(read.session_id, read.otp)
    if not success:
        return RedemptionOutcome("rejected", message=message)
    return RedemptionOutcome("open_files", source=source, files=files, message=message)


class DuplicateReadFilter:
    """Drops an identical payload repeated within a few seconds, so one
    accidental double read doesn't show a 'code already used' error. Suppressed
    repeats don't extend the window."""

    def __init__(self, window_seconds=DUPLICATE_WINDOW_SECONDS, clock=time.monotonic):
        self._window = window_seconds
        self._clock = clock
        self._last_text = None
        self._last_time = 0.0

    def is_duplicate(self, text: str) -> bool:
        now = self._clock()
        if text == self._last_text and now - self._last_time < self._window:
            return True
        self._last_text, self._last_time = text, now
        return False


class QrReaderManager:
    """Reads CR-terminated lines from an open serial port on a daemon thread and
    calls `on_read(text)` once per non-empty read. Stray LFs are dropped."""

    def __init__(self, port, on_read):
        self._port = port
        self._on_read = on_read
        self._thread = None
        self._stop_event = threading.Event()

    @classmethod
    def from_config(cls, on_read):
        """Returns None when QR_READER_PORT is blank (reader off) or can't be opened."""
        port_name = get_config().qr_reader_port
        if not port_name:
            return None
        if serial is None:
            print("⚠️ QR_READER_PORT is set but pyserial is not installed; QR reader off")
            return None
        try:
            port = serial.serial_for_url(port_name, baudrate=READER_BAUDRATE,
                                         timeout=_POLL_TIMEOUT_SECONDS)
        except (serial.SerialException, OSError, ValueError) as e:
            print(f"⚠️ Could not open QR reader port '{port_name}': {e}")
            return None
        return cls(port, on_read)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="qr-reader", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
            self._thread = None
        try:
            self._port.close()
        except Exception as e:
            print(f"⚠️ Error closing QR reader port: {e}")

    def _run(self):
        buffer = b""
        while not self._stop_event.is_set():
            try:
                buffer += self._port.read(self._port.in_waiting or 1)
            except Exception as e:
                print(f"⚠️ QR reader port error, reader stopped: {e}")
                return
            while b"\r" in buffer:
                line, buffer = buffer.split(b"\r", 1)
                text = line.replace(b"\n", b"").decode("ascii", errors="replace")
                if text:
                    self._emit(text)

    def _emit(self, text):
        try:
            self._on_read(text)
        except Exception as e:
            print(f"⚠️ QR read handler failed: {e}")
