"""
Seam tests for the kiosk heartbeat and QR reader status written to the settings
table (issue #42). Pure functions and a real temp DatabaseManager — no Qt event
loop, no serial port.
"""
from datetime import datetime

import pytest

from database.db_manager import DatabaseManager
from database.models import init_db
from managers import kiosk_status
from managers.kiosk_status import (SETTING_LAST_SEEN, SETTING_QR_STATUS, heartbeat_timestamp, write_heartbeat,
                                    write_qr_status)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    manager = DatabaseManager(db_path=path)
    yield manager
    manager.close()


class _FailingDB:
    def update_setting(self, key, value):
        raise RuntimeError("boom")


class TestHeartbeatTimestamp:
    def test_is_iso_8601_round_trippable(self):
        now = datetime(2026, 10, 22, 14, 30, 5)
        value = heartbeat_timestamp(now)
        # ISO 8601, seconds precision, no microseconds
        assert value == "2026-10-22T14:30:05"
        assert datetime.fromisoformat(value) == now

    def test_defaults_to_current_time(self):
        value = heartbeat_timestamp()
        # Parses as a valid timestamp
        assert datetime.fromisoformat(value)


class TestWriteHeartbeat:
    def test_persists_timestamp(self, db):
        now = datetime(2026, 1, 2, 3, 4, 5)
        assert write_heartbeat(db, now) is True
        assert db.get_setting(SETTING_LAST_SEEN) == "2026-01-02T03:04:05"

    def test_refresh_overwrites(self, db):
        write_heartbeat(db, datetime(2026, 1, 1, 0, 0, 0))
        write_heartbeat(db, datetime(2026, 1, 1, 0, 1, 0))
        assert db.get_setting(SETTING_LAST_SEEN) == "2026-01-01T00:01:00"

    def test_failed_write_is_logged_and_swallowed(self, monkeypatch):
        logged = []
        monkeypatch.setattr(kiosk_status, "log_error",
                            lambda *a, **k: logged.append(a), raising=False)
        assert write_heartbeat(_FailingDB(), datetime.now()) is False
        assert logged  # the failure was logged, not raised


class TestWriteQrStatus:
    @pytest.mark.parametrize("text", ["Connected", "Not connected", "Not configured", "Starting"])
    def test_persists_status_text(self, db, text):
        assert write_qr_status(db, text) is True
        assert db.get_setting(SETTING_QR_STATUS) == text

    def test_failed_write_is_logged_and_swallowed(self, monkeypatch):
        logged = []
        monkeypatch.setattr(kiosk_status, "log_error",
                            lambda *a, **k: logged.append(a), raising=False)
        assert write_qr_status(_FailingDB(), "Connected") is False
        assert logged


class TestDbThreaderUpdateSetting:
    """The db_threader handler (used by the heartbeat/QR writes) persists the
    value through the worker's DatabaseManager. Called directly — no thread,
    no Qt event loop."""

    def test_handler_persists_value(self, db):
        from managers.db_threader import DatabaseOperation, DatabaseThreadManager
        manager = DatabaseThreadManager()
        manager.db_manager = db
        op = DatabaseOperation("update_setting",
                               {'key': SETTING_LAST_SEEN, 'value': "2026-01-02T03:04:05"})
        manager._handle_update_setting(op)
        assert op.result is True
        assert db.get_setting(SETTING_LAST_SEEN) == "2026-01-02T03:04:05"
