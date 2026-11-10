"""
The kiosk's scheduled sweep of past-expiry intake Sessions (issue #108):
main_app runs SessionManager.cleanup_expired_sessions() once at startup and then
every 5 minutes on a QTimer, and stops that timer in cleanup().

Driven on a bare stand-in for the app with a fake QTimer, so nothing waits on a
real 5-minute clock and no GUI is created.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import main_app  # noqa: E402
from main_app import PrintingSystemApp, SESSION_CLEANUP_INTERVAL_MS  # noqa: E402


class FakeTimer:
    """Records what main_app asked of it; never fires on its own."""
    instances = []

    def __init__(self, *args, **kwargs):
        self.started_with = None
        self.stopped = False
        self.timeout = SimpleNamespace(connect=self._connect)
        self.slots = []
        FakeTimer.instances.append(self)

    def _connect(self, slot):
        self.slots.append(slot)

    def start(self, ms):
        self.started_with = ms

    def stop(self):
        self.stopped = True

    def fire(self):
        for slot in self.slots:
            slot()


@pytest.fixture
def timers(monkeypatch):
    FakeTimer.instances = []
    monkeypatch.setattr(main_app, 'QTimer', FakeTimer)
    return FakeTimer


class FakeSessionManager:
    def __init__(self, batches=None):
        self.batches = list(batches or [])
        self.calls = 0
        self.raise_on_call = None

    def cleanup_expired_sessions(self):
        self.calls += 1
        if self.raise_on_call is not None and self.calls == self.raise_on_call:
            raise RuntimeError("db is busy")
        return self.batches.pop(0) if self.batches else 0


def app_with(session_manager):
    return SimpleNamespace(session_cleanup_manager=session_manager)


def bare_app(**attrs):
    """A stand-in app whose methods are PrintingSystemApp's own, unbound."""
    app = SimpleNamespace(**attrs)
    app._run_session_cleanup = lambda: PrintingSystemApp._run_session_cleanup(app)
    return app


@pytest.fixture
def fake_session_managers(monkeypatch):
    """main_app builds its own SessionManager(DatabaseManager()); swap in a fake."""
    built = []

    def make(batches=None):
        manager = FakeSessionManager(batches)
        built.append(manager)
        monkeypatch.setattr(main_app, 'SessionManager', lambda *a, **k: manager)
        monkeypatch.setattr(main_app, 'DatabaseManager', lambda *a, **k: object())
        return manager

    return make


class TestSetup:
    def test_runs_one_pass_at_startup(self, timers, fake_session_managers):
        manager = fake_session_managers([2])

        PrintingSystemApp._setup_session_cleanup(bare_app())

        assert manager.calls == 1

    def test_schedules_a_pass_every_five_minutes(self, timers, fake_session_managers):
        fake_session_managers()
        app = bare_app()

        PrintingSystemApp._setup_session_cleanup(app)

        timer = FakeTimer.instances[0]
        assert SESSION_CLEANUP_INTERVAL_MS == 5 * 60 * 1000
        assert timer.started_with == 5 * 60 * 1000
        assert app._session_cleanup_timer is timer
        assert timer.slots == [app._run_session_cleanup]

    def test_each_tick_runs_another_pass(self, timers, fake_session_managers):
        manager = fake_session_managers()
        PrintingSystemApp._setup_session_cleanup(bare_app())
        assert manager.calls == 1

        FakeTimer.instances[0].fire()
        FakeTimer.instances[0].fire()

        assert manager.calls == 3


class TestPass:
    def test_prints_the_count_only_when_something_was_removed(self, capsys):
        app = app_with(FakeSessionManager([0, 3]))

        PrintingSystemApp._run_session_cleanup(app)
        assert "session" not in capsys.readouterr().out

        PrintingSystemApp._run_session_cleanup(app)
        assert "Removed 3 expired session(s)" in capsys.readouterr().out

    def test_a_failure_is_reported_and_does_not_raise(self, capsys):
        manager = FakeSessionManager()
        manager.raise_on_call = 1
        app = app_with(manager)

        PrintingSystemApp._run_session_cleanup(app)  # must not raise

        assert "Session cleanup failed" in capsys.readouterr().out


class TestCleanup:
    def _stubbed_app(self, monkeypatch):
        # Everything else cleanup() touches, kept out of the way.
        monkeypatch.setattr(main_app, 'cleanup_sms', lambda: None)
        monkeypatch.setattr(main_app, 'cleanup_persistent_gpio', lambda: None)
        monkeypatch.setattr('utils.error_logger.cleanup_db_connections', lambda: None)
        timer = FakeTimer(None)
        app = SimpleNamespace(_stop_hoppers=lambda: None, _session_cleanup_timer=timer)
        return app, timer

    def test_stops_the_timer(self, monkeypatch):
        app, timer = self._stubbed_app(monkeypatch)

        PrintingSystemApp.cleanup(app)

        assert timer.stopped is True
