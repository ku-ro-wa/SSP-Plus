"""SMS alerts go to PHONE_NUMBER from .env, and nowhere when it isn't set.

The SMS code used to ignore PHONE_NUMBER and text a number hardcoded in
sms_manager.py.
"""
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
        assert manager.send_sms("Printer jam") is False
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
