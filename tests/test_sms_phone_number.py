"""SMS alerts go to PHONE_NUMBER from .env, and nowhere when it isn't set.

The SMS code used to ignore PHONE_NUMBER and text a number hardcoded in
sms_manager.py.
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from managers import sms_manager as sms


@pytest.fixture(autouse=True)
def fresh_manager(monkeypatch):
    monkeypatch.setattr(sms, "sms_manager", None)
    yield
    sms.sms_manager = None


@pytest.mark.parametrize("value", ["09171234567", "+639171234567"])
def test_number_comes_from_env(monkeypatch, value):
    monkeypatch.setenv("PHONE_NUMBER", value)
    assert sms.configured_phone_number() == value
    assert sms.get_sms_manager().phone_number == value


@pytest.mark.parametrize("value", ["", "   ", "09XXXXXXXXX", "not a number"])
def test_blank_or_placeholder_means_no_number(monkeypatch, value):
    monkeypatch.setenv("PHONE_NUMBER", value)
    assert sms.configured_phone_number() is None


def test_unset_means_no_number(monkeypatch):
    monkeypatch.delenv("PHONE_NUMBER", raising=False)
    assert sms.configured_phone_number() is None
    assert sms.get_sms_manager().phone_number is None


def test_no_hardcoded_default():
    assert sms.SMSManager().phone_number is None


@pytest.mark.parametrize("sim_mode", ["true", "false"])
def test_no_number_sends_nothing(monkeypatch, sim_mode):
    monkeypatch.delenv("PHONE_NUMBER", raising=False)
    monkeypatch.setenv("SIM_MODE", sim_mode)
    fake_serial = MagicMock()
    with patch.object(sms, "serial", fake_serial), patch.object(sms, "SERIAL_AVAILABLE", True):
        manager = sms.get_sms_manager()
        assert manager.send_sms_and_close("Printer jam") is False
    fake_serial.Serial.assert_not_called()


class FakeModem:
    """A serial port that answers like a SIM800L: OK to setup commands, '> ' to
    AT+CMGS (or `prompt`), and `network` once the message's Ctrl+Z arrives,
    `network_delay` seconds later. Each empty read advances the fake clock 1 s."""

    def __init__(self, network=b"\r\n+CMGS: 12\r\n\r\nOK\r\n", network_delay=0, prompt=b"\r\n> "):
        self.network, self.network_delay, self.prompt = network, network_delay, prompt
        self.now = 0.0
        self.written = b""
        self.buffer = b""
        self.pending = None   # (time, bytes) the network answers at
        self.is_open = True

    # serial.Serial(...) returns this port
    def __call__(self, *args, **kwargs):
        return self

    def write(self, data):
        self.written += data
        if data.startswith(b"AT+CMGS="):
            self.buffer += self.prompt
        elif data.endswith(bytes([26])):
            self.pending = (self.now + self.network_delay, self.network)
        elif data.startswith(b"AT"):
            self.buffer += b"\r\nOK\r\n"

    @property
    def in_waiting(self):
        self._deliver()
        return len(self.buffer)

    def _deliver(self):
        if self.pending and self.now >= self.pending[0]:
            self.buffer += self.pending[1]
            self.pending = None

    def read(self, n=1):
        self._deliver()
        if not self.buffer:
            self.now += 1     # a read with nothing to read waits the 1 s timeout
            return b""
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return out

    def reset_input_buffer(self):
        self.buffer = b""

    def flush(self):
        pass

    def close(self):
        self.is_open = False


@pytest.fixture
def port(monkeypatch):
    monkeypatch.setenv("PHONE_NUMBER", "09171234567")
    monkeypatch.setenv("SIM_MODE", "false")
    fake = FakeModem()
    fake_serial = MagicMock()
    fake_serial.Serial = fake
    monkeypatch.setattr(sms, "serial", fake_serial)
    monkeypatch.setattr(sms, "SERIAL_AVAILABLE", True)
    monkeypatch.setattr(sms.time, "sleep", lambda s: setattr(fake, "now", fake.now + s))
    monkeypatch.setattr(sms.time, "monotonic", lambda: fake.now)
    return fake


def test_number_is_what_the_modem_is_given(port):
    assert sms.get_sms_manager().send_sms_and_close("Printer jam") is True
    assert b'AT+CMGS="09171234567"' in port.written
    assert b"09762912863" not in port.written
    assert port.written.endswith(b"Printer jam" + bytes([26]))
    assert not port.is_open


def test_a_slow_network_answer_still_counts(port):
    """Globe took ~45 s to answer one send; the old fixed 15 s wait gave up on it."""
    port.network_delay = 45
    manager = sms.get_sms_manager()
    assert manager.send_sms_and_close("Printer jam") is True
    assert manager.last_error is None


def test_the_network_refusing_it_is_reported(port):
    port.network, port.network_delay = b"\r\n+CMS ERROR: User busy\r\n", 44
    manager = sms.get_sms_manager()
    assert manager.send_sms_and_close("Printer jam") is False
    assert manager.last_error == "Network refused it: +CMS ERROR: User busy"


def test_no_answer_gives_up_after_the_timeout(port):
    port.network, port.network_delay = b"", 0
    manager = sms.get_sms_manager()
    started = port.now
    assert manager.send_sms_and_close("Printer jam") is False
    assert "No answer" in manager.last_error
    assert port.now - started < sms.SMSManager.SEND_TIMEOUT + 15


def test_a_refused_number_sends_nothing(port):
    port.prompt = b"\r\nERROR\r\n"
    manager = sms.get_sms_manager()
    assert manager.send_sms_and_close("Printer jam") is False
    assert "Printer jam" not in port.written.decode()
    assert port.written.endswith(bytes([27]))   # cancelled with Esc
    assert manager.last_error.startswith("Modem refused the number")


def test_echo_is_off_before_the_message_is_sent(port):
    sms.get_sms_manager().send_sms_and_close("Printing error: ERROR 5")
    assert port.written.index(b"ATE0") < port.written.index(b"AT+CMGS")


def test_the_reason_goes_into_error_log(monkeypatch, port):
    port.network = b"\r\n+CMS ERROR: User busy\r\n"
    logged = []
    monkeypatch.setattr(sms, "_log_send_failure", lambda m, reason=None: logged.append((m, reason)))
    sms.send_operator_alert("Printer jam")
    _wait_for_senders()
    assert logged == [("Printer jam", "Network refused it: +CMS ERROR: User busy")]


# --- Sending never blocks the caller -------------------------------------

class _Modem:
    """Stands in for the modem send: records messages, answers with `result`,
    and can be held mid-send with `gate`."""

    def __init__(self):
        self.result = True
        self.sent = []
        self.logged = []
        self.gate = threading.Event()
        self.gate.set()

    def send(self, message):
        self.gate.wait(5)
        self.sent.append(message)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def modem(monkeypatch):
    monkeypatch.setenv("PHONE_NUMBER", "09171234567")
    fake = _Modem()
    monkeypatch.setattr(sms.SMSManager, "send_sms_and_close",
                        lambda self, message: fake.send(message))
    monkeypatch.setattr(sms, "_log_send_failure",
                        lambda message, reason=None: fake.logged.append((message, reason)))
    return fake


def _wait_for_senders():
    for t in threading.enumerate():
        if t.name == "operator-sms":
            t.join(timeout=5)


@pytest.mark.parametrize("send, expected", [
    (lambda: sms.send_paper_jam_sms(), "Printer jam"),
    (lambda: sms.send_no_paper_sms(), "Printer is out of paper. Please refill."),
    (lambda: sms.send_low_paper_sms(), "Low paper, please refill."),
    (lambda: sms.send_printing_error_sms("Printer is offline"), "Printing error: Printer is offline"),
    (lambda: sms.send_operator_alert("Hopper failure"), "Hopper failure"),
])
def test_every_alert_goes_out_in_the_background(modem, send, expected):
    modem.gate.clear()          # the modem is still "sending"...
    send()                      # ...but the caller is already back
    assert modem.sent == []
    modem.gate.set()
    _wait_for_senders()
    assert modem.sent == [expected]


def test_no_number_starts_no_thread(monkeypatch):
    monkeypatch.delenv("PHONE_NUMBER", raising=False)
    started = []
    monkeypatch.setattr(sms.threading, "Thread", lambda *a, **k: started.append(1))
    sms.send_operator_alert("Printer jam")
    assert started == []


def test_a_failed_send_is_logged(modem):
    modem.result = False
    sms.send_operator_alert("Printer jam")
    _wait_for_senders()
    assert [m for m, _ in modem.logged] == ["Printer jam"]


def test_a_send_that_raises_is_logged(modem):
    modem.result = RuntimeError("port gone")
    sms.send_operator_alert("Printer jam")
    _wait_for_senders()
    assert [m for m, _ in modem.logged] == ["Printer jam"]


def test_a_confirmed_send_logs_nothing(modem):
    sms.send_operator_alert("Printer jam")
    _wait_for_senders()
    assert modem.sent == ["Printer jam"] and modem.logged == []


def test_alerts_go_out_one_at_a_time(monkeypatch):
    monkeypatch.setenv("PHONE_NUMBER", "09171234567")
    monkeypatch.setattr(sms, "_log_send_failure", lambda message, reason=None: None)
    active, overlap = [0], []

    def send(self, message):
        active[0] += 1
        overlap.append(active[0])
        time.sleep(0.05)
        active[0] -= 1
        return True
    monkeypatch.setattr(sms.SMSManager, "send_sms_and_close", send)

    for i in range(3):
        sms.send_operator_alert(f"alert {i}")
    _wait_for_senders()
    assert overlap == [1, 1, 1]
