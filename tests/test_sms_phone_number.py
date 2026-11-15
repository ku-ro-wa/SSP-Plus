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


def test_number_is_what_the_modem_is_given(monkeypatch):
    monkeypatch.setenv("PHONE_NUMBER", "09171234567")
    monkeypatch.setenv("SIM_MODE", "false")
    port = MagicMock()
    port.read.return_value = b"+CMGS: 1\r\nOK"
    fake_serial = MagicMock()
    fake_serial.Serial.return_value = port
    with patch.object(sms, "serial", fake_serial), patch.object(sms, "SERIAL_AVAILABLE", True), \
            patch.object(sms.time, "sleep"):
        assert sms.get_sms_manager().send_sms_and_close("Printer jam") is True
    written = b"".join(call.args[0] for call in port.write.call_args_list)
    assert b'AT+CMGS="09171234567"' in written
    assert b"09762912863" not in written


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
    monkeypatch.setattr(sms, "_log_send_failure", fake.logged.append)
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
    assert modem.logged == ["Printer jam"]


def test_a_send_that_raises_is_logged(modem):
    modem.result = RuntimeError("port gone")
    sms.send_operator_alert("Printer jam")
    _wait_for_senders()
    assert modem.logged == ["Printer jam"]


def test_a_confirmed_send_logs_nothing(modem):
    sms.send_operator_alert("Printer jam")
    _wait_for_senders()
    assert modem.sent == ["Printer jam"] and modem.logged == []


def test_alerts_go_out_one_at_a_time(monkeypatch):
    monkeypatch.setenv("PHONE_NUMBER", "09171234567")
    monkeypatch.setattr(sms, "_log_send_failure", lambda message: None)
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
