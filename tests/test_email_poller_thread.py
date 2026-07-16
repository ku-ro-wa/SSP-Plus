"""
Tests for EmailPollerThreadManager — no real IMAP/SMTP/DB. The threading
behavior tests use a FakeAdapter with a threading.Event so they wait on an
actual signal rather than guessing sleep durations. The from_config() test
overrides EMAIL_UPLOAD_DIR via monkeypatch.setenv so it never touches the
real repo path, and never calls poll_inbox so no real IMAP connection is
attempted.
"""
import os
import threading
import time

from managers.email_poller_thread import EmailPollerThreadManager
from tests.test_session_manager import FakeDBManager


class FakeAdapter:
    def __init__(self, raise_on_call=None):
        self.call_count = 0
        self.raise_on_call = raise_on_call
        self._lock = threading.Lock()
        self.event = threading.Event()

    def poll_inbox(self):
        with self._lock:
            self.call_count += 1
            count = self.call_count
        self.event.set()
        if self.raise_on_call is not None and count == self.raise_on_call:
            raise RuntimeError("simulated poll failure")


def _wait_for_count(adapter, minimum, timeout=1.0):
    deadline = time.time() + timeout
    while adapter.call_count < minimum and time.time() < deadline:
        time.sleep(0.01)
    return adapter.call_count


class TestEmailPollerThreadManager:
    def test_start_polls_immediately(self):
        adapter = FakeAdapter()
        manager = EmailPollerThreadManager(adapter, poll_interval_seconds=10)
        manager.start()
        try:
            assert adapter.event.wait(timeout=1.0)
            assert adapter.call_count >= 1
        finally:
            manager.stop()

    def test_polls_repeatedly_at_interval(self):
        adapter = FakeAdapter()
        manager = EmailPollerThreadManager(adapter, poll_interval_seconds=0.02)
        manager.start()
        try:
            assert _wait_for_count(adapter, 3) >= 3
        finally:
            manager.stop()

    def test_stop_halts_further_polling(self):
        adapter = FakeAdapter()
        manager = EmailPollerThreadManager(adapter, poll_interval_seconds=0.02)
        manager.start()
        assert adapter.event.wait(timeout=1.0)
        manager.stop()
        count_after_stop = adapter.call_count
        time.sleep(0.1)
        assert adapter.call_count == count_after_stop

    def test_exception_in_poll_cycle_does_not_kill_loop(self):
        adapter = FakeAdapter(raise_on_call=1)
        manager = EmailPollerThreadManager(adapter, poll_interval_seconds=0.02)
        manager.start()
        try:
            assert _wait_for_count(adapter, 2) >= 2  # survived the raise, polled again
        finally:
            manager.stop()

    def test_thread_is_daemon(self):
        adapter = FakeAdapter()
        manager = EmailPollerThreadManager(adapter, poll_interval_seconds=10)
        manager.start()
        try:
            assert manager.thread.daemon is True
        finally:
            manager.stop()


class TestFromConfig:
    def test_builds_adapter_from_env_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EMAIL_UPLOAD_DIR", str(tmp_path / "email_uploads"))
        monkeypatch.setenv("EMAIL_POLL_INTERVAL_SECONDS", "42")
        monkeypatch.setenv("EMAIL_SUBJECT_KEYWORD", "CUSTOM_KEYWORD")

        db = FakeDBManager()
        manager = EmailPollerThreadManager.from_config(db_manager=db)

        assert manager.poll_interval_seconds == 42
        assert manager.email_adapter.subject_keyword == "CUSTOM_KEYWORD"
        assert manager.email_adapter.upload_dir == str(tmp_path / "email_uploads")
        assert os.path.isdir(manager.email_adapter.upload_dir)
