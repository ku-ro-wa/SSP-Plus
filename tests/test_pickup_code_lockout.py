"""Typed pickup-code attempt limit (issue #104).

The counter is pure logic on a temp SQLite file and a fake clock — no Qt event
loop needed. The Wi-Fi/Email model tests only need a QApplication for the
models' signals; no screen is shown.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

from database.db_manager import DatabaseManager
from database.models import init_db
from managers.pickup_code_lockout import (
    DEFAULT_LOCKOUT_MINUTES, DEFAULT_MAX_ATTEMPTS, ERROR_SOURCE, PickupCodeLockout,
    locked_message,
)
from managers.session_manager import SessionManager
from screens.email.model import EmailModel
from screens.wifi.model import WifiModel

FILES = [{"path": "/tmp/fake/upload.pdf", "original_filename": "upload.pdf"}]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(tmp_path):
    path = str(tmp_path / "pickup.db")
    init_db(path)
    clock = Clock()
    dbs = []

    def db():
        d = DatabaseManager(db_path=path)
        dbs.append(d)
        return d

    def lockout(manager=None, **kwargs):
        return PickupCodeLockout(manager or db(), clock=clock, **kwargs)

    yield db, lockout, clock

    for d in dbs:
        d.close()


def _wrong(real_otp):
    """Any 6-digit code that isn't the session's."""
    candidate = str((int(real_otp) + 1) % 1_000_000).zfill(6)
    return candidate


def _create(db, source="wifi"):
    return SessionManager(db).create_session(source, FILES)


def _results(model, codes):
    """[(success, message, files), ...] for each validated code, in order."""
    seen = []
    model.otp_result.connect(lambda ok, msg, files: seen.append((ok, msg, files)))
    for code in codes:
        model.validate_otp(code)
    return seen


class TestLockoutCounter:
    def test_fifth_wrong_code_locks(self, env):
        _, lockout, _ = env
        lo = lockout()
        for _ in range(DEFAULT_MAX_ATTEMPTS - 1):
            assert lo.record_failure() is False
        assert not lo.is_locked()
        assert lo.record_failure() is True
        assert lo.is_locked()
        assert lo.remaining() == 300

    def test_success_resets_the_counter(self, env):
        _, lockout, _ = env
        lo = lockout()
        for _ in range(4):
            lo.record_failure()
        lo.record_success()
        for _ in range(4):
            lo.record_failure()
        assert not lo.is_locked()

    def test_lock_is_a_stored_wall_clock_deadline(self, env):
        db, lockout, clock = env
        for _ in range(DEFAULT_MAX_ATTEMPTS):
            lockout().record_failure()

        # A fresh connection behaves like a restarted app: deadline and count
        # are read back from the settings table, not held in memory.
        revived = lockout(db())
        assert revived.is_locked()
        assert revived.remaining() == 300
        clock.advance(minutes=DEFAULT_LOCKOUT_MINUTES, seconds=-1)
        assert lockout().is_locked()
        clock.advance(seconds=1)
        assert not lockout().is_locked()

    def test_partial_counter_survives_a_new_instance(self, env):
        db, lockout, _ = env
        for _ in range(3):
            lockout().record_failure()
        lo = lockout(db())
        lo.record_failure()
        assert lo.record_failure() is True

    def test_lockout_minutes_setting(self, env):
        db, lockout, clock = env
        db().update_setting("pickup_code_lockout_minutes", 1)
        lo = lockout()
        for _ in range(DEFAULT_MAX_ATTEMPTS):
            lo.record_failure()
        assert lo.remaining() == 60
        clock.advance(minutes=1)
        assert not lo.is_locked()

    def test_max_attempts_setting(self, env):
        db, lockout, _ = env
        db().update_setting("pickup_code_max_attempts", 2)
        lo = lockout()
        assert lo.record_failure() is False
        assert lo.record_failure() is True
        assert lo.is_locked()

    def test_one_error_log_row_per_lockout(self, env):
        db, lockout, clock = env
        lo = lockout()
        for _ in range(DEFAULT_MAX_ATTEMPTS):
            lo.record_failure()
        rows = [r for r in db().get_error_log() if r["error_type"] == ERROR_SOURCE]
        assert len(rows) == 1

        clock.advance(minutes=DEFAULT_LOCKOUT_MINUTES)
        for _ in range(DEFAULT_MAX_ATTEMPTS):
            lo.record_failure()
        rows = [r for r in db().get_error_log() if r["error_type"] == ERROR_SOURCE]
        assert len(rows) == 2

    def test_locked_message_counts_down(self):
        assert locked_message(272) == "Too many wrong codes. Try again in 4:32."
        assert locked_message(300) == "Too many wrong codes. Try again in 5:00."


class TestWifiScreen:
    def test_five_wrong_typed_codes_lock_and_reject_the_right_one(self, env):
        db, lockout, _ = env
        session = _create(db())
        model = WifiModel(db_manager=db(), lockout=lockout())
        codes = [_wrong(session.otp)] * DEFAULT_MAX_ATTEMPTS

        seen = _results(model, codes)

        assert [ok for ok, _, _ in seen] == [False] * DEFAULT_MAX_ATTEMPTS
        assert "Too many wrong codes" in seen[-1][1]
        assert model.lock_remaining() == 300

        # The correct code is refused while the lock runs, and doesn't count.
        seen = _results(model, [session.otp])
        assert seen == [(False, locked_message(model.lock_remaining()), [])]

    def test_correct_code_resets_the_counter(self, env):
        db, lockout, _ = env
        session = _create(db())
        model = WifiModel(db_manager=db(), lockout=lockout())
        wrong = _wrong(session.otp)

        _results(model, [wrong] * 4)
        seen = _results(model, [session.otp])
        assert seen[0][0] is True
        assert [f["original_filename"] for f in seen[0][2]] == ["upload.pdf"]

        _results(model, [wrong] * 4)
        assert model.lock_remaining() == 0

    def test_correct_code_works_once_the_lock_expires(self, env):
        db, lockout, clock = env
        session = _create(db())
        model = WifiModel(db_manager=db(), lockout=lockout())
        _results(model, [_wrong(session.otp)] * DEFAULT_MAX_ATTEMPTS)

        clock.advance(minutes=DEFAULT_LOCKOUT_MINUTES)
        seen = _results(model, [session.otp])
        assert seen[0][0] is True
        assert model.lock_remaining() == 0

    def test_malformed_input_does_not_count(self, env):
        db, lockout, _ = env
        model = WifiModel(db_manager=db(), lockout=lockout())
        for _ in range(DEFAULT_MAX_ATTEMPTS + 2):
            for text in ("", "12", "1234567", "abcdef"):
                model.validate_otp(text)
        assert model.lock_remaining() == 0

    def test_real_but_locked_out_session_does_not_count(self, env):
        db, lockout, _ = env
        manager = db()
        session = _create(manager)
        manager.set_session_status(session.session_id, "locked")
        model = WifiModel(db_manager=manager, lockout=lockout())
        seen = _results(model, [session.otp] * (DEFAULT_MAX_ATTEMPTS + 1))
        assert all("locked" in message.lower() for _, message, _ in seen)
        assert model.lock_remaining() == 0

    def test_a_used_code_opens_again_and_does_not_count(self, env):
        # Reusable until expiry (#111): retyping a code already used must open
        # the files again, and never count toward the lockout.
        db, lockout, _ = env
        session = _create(db())
        model = WifiModel(db_manager=db(), lockout=lockout())

        seen = _results(model, [session.otp] * (DEFAULT_MAX_ATTEMPTS + 1))

        assert all(ok is True for ok, _, _ in seen)
        assert model.lock_remaining() == 0

    def test_a_used_code_typed_on_the_other_screen_does_not_count(self, env):
        db, lockout, _ = env
        manager = db()
        email_session = _create(manager, "email")
        email = EmailModel(db_manager=manager, lockout=lockout())
        assert _results(email, [email_session.otp])[0][0] is True
        wifi = WifiModel(db_manager=manager, lockout=lockout())

        seen = _results(wifi, [email_session.otp] * (DEFAULT_MAX_ATTEMPTS + 1))

        assert all(ok is False for ok, _, _ in seen)
        assert wifi.lock_remaining() == 0

    def test_code_for_the_other_upload_screen_does_not_count(self, env):
        db, lockout, _ = env
        manager = db()
        email_session = _create(manager, "email")
        wifi = WifiModel(db_manager=manager, lockout=lockout())

        seen = _results(wifi, [email_session.otp] * (DEFAULT_MAX_ATTEMPTS + 1))

        assert all(ok is False for ok, _, _ in seen)
        assert wifi.lock_remaining() == 0

    def test_lockout_is_logged_once_however_many_attempts(self, env):
        db, lockout, _ = env
        model = WifiModel(db_manager=db(), lockout=lockout())
        _results(model, ["000000"] * DEFAULT_MAX_ATTEMPTS)
        _results(model, ["000001"] * 3)
        rows = [r for r in db().get_error_log() if r["error_type"] == ERROR_SOURCE]
        assert len(rows) == 1


class TestSharedCounter:
    def test_email_screen_is_locked_by_misses_at_wifi(self, env):
        db, lockout, _ = env
        manager = db()
        wifi = WifiModel(db_manager=manager, lockout=lockout())
        _results(wifi, ["000000"] * DEFAULT_MAX_ATTEMPTS)

        session = _create(manager, "email")
        email = EmailModel(db_manager=manager, lockout=lockout())
        seen = _results(email, [session.otp])
        assert seen[0][0] is False
        assert "Too many wrong codes" in seen[0][1]


class TestScreenWiring:
    """The controllers mirror the stored deadline into the view: keypad dead,
    banner counting down, and both cleared when the lock expires."""

    @pytest.mark.parametrize("module_name,model_name", [
        ("screens.wifi.controller", "WifiModel"),
        ("screens.email.controller", "EmailModel"),
    ])
    def test_controller_locks_and_unlocks_the_view(self, monkeypatch, qapp, module_name, model_name):
        import importlib

        module = importlib.import_module(module_name)
        model = MagicMock()
        model.lock_remaining.return_value = 300
        monkeypatch.setattr(module, model_name, lambda: model)

        screen_name = module_name.split(".")[1]  # screens.<name>.controller
        controller_class = getattr(module, screen_name.capitalize() + "Controller")
        main_app = SimpleNamespace(webapp_thread=None)
        controller = controller_class(main_app)
        controller.on_enter()

        assert not controller.view.otp_input.isEnabled()
        assert "Try again in 5:00" in controller.view.status_banner._label.text()
        assert controller._lock_timer.isActive()

        model.lock_remaining.return_value = 0
        controller._refresh_lock()

        assert controller.view.otp_input.isEnabled()
        assert controller.view.status_banner.isHidden()
        assert not controller._lock_timer.isActive()
