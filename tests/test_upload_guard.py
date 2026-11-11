"""Per-phone upload limit and storage floor on the Portal's POST /upload.

Logic on a fake clock and fake free space, then the real app over TestClient
with the guard swapped in, to check the refusal happens before the files are
handled and what the phone sees.
"""
import sys

import pytest
from fastapi.testclient import TestClient

from webapp.upload_guard import STORAGE_FULL_MESSAGE, UploadGuard

MB = 1024 * 1024


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_guard(clock=None, free=10_000 * MB, **kwargs):
    logged = []
    guard = UploadGuard(
        "unused", uploads_per_phone=3, window_minutes=10, min_free_mb=1024,
        clock=clock or Clock(), free_bytes=lambda _p: free,
        log_error=lambda *args: logged.append(args), **kwargs,
    )
    return guard, logged


class TestPerPhoneLimit:
    def test_limit_then_wait(self):
        clock = Clock()
        guard, _ = make_guard(clock)
        for _ in range(3):
            assert guard.check("10.0.0.5", 1 * MB) is None
        status, message, retry = guard.check("10.0.0.5", 1 * MB)
        assert status == 429 and retry == 600
        assert "Too many uploads" in message and "10 minute" in message

        clock.now += 599
        assert guard.check("10.0.0.5", 1 * MB)[0] == 429
        clock.now += 1
        assert guard.check("10.0.0.5", 1 * MB) is None

    def test_phones_are_counted_separately(self):
        guard, _ = make_guard()
        for _ in range(3):
            guard.check("10.0.0.5", 0)
        assert guard.check("10.0.0.5", 0)[0] == 429
        assert guard.check("10.0.0.6", 0) is None

    def test_refused_requests_do_not_extend_the_wait(self):
        clock = Clock()
        guard, _ = make_guard(clock)
        for _ in range(3):
            guard.check("p", 0)
        for _ in range(20):
            clock.now += 10
            guard.check("p", 0)
        clock.now = 1000.0 + 600
        assert guard.check("p", 0) is None


class TestStorageFloor:
    def test_refused_when_upload_would_cross_the_floor(self):
        guard, _ = make_guard(free=1100 * MB)
        assert guard.check("p", 50 * MB) is None
        status, message, retry = guard.check("p", 100 * MB)
        assert (status, message, retry) == (507, STORAGE_FULL_MESSAGE, None)

    def test_storage_refusal_does_not_count_against_the_phone(self):
        guard, _ = make_guard(free=500 * MB)
        for _ in range(5):
            assert guard.check("p", 0)[0] == 507
        guard.free_bytes = lambda _p: 10_000 * MB
        assert guard.check("p", 0) is None

    def test_logged_once_an_hour(self):
        clock = Clock()
        guard, logged = make_guard(clock, free=500 * MB)
        for _ in range(5):
            guard.check("p", 0)
        assert len(logged) == 1
        assert logged[0][0] == "Wi-Fi Portal" and "500 MB free" in logged[0][1]
        clock.now += 3600
        guard.check("p", 0)
        assert len(logged) == 2

    def test_unreadable_storage_lets_the_upload_through(self):
        def broken(_p):
            raise OSError("no disk")
        guard, _ = make_guard()
        guard.free_bytes = broken
        assert guard.check("p", 0) is None

    def test_missing_upload_dir_uses_its_parent(self, tmp_path):
        from webapp.upload_guard import free_bytes
        assert free_bytes(str(tmp_path / "not" / "made" / "yet")) > 0


class TestRoute:
    @pytest.fixture
    def app_with(self, monkeypatch):
        from webapp.main import app

        def install(guard):
            monkeypatch.setattr(sys.modules["webapp.main"], "upload_guard", guard)
            return TestClient(app)
        return install

    def test_limit_refuses_before_the_files_are_handled(self, app_with):
        guard, _ = make_guard()
        client = app_with(guard)
        handled = []
        from webapp.dependencies import get_wifi_adapter
        from webapp.main import app

        class Adapter:
            def handle_upload(self, uploads, metadata=None):
                handled.append(len(uploads))
                return False, "not a valid PDF", None

        app.dependency_overrides[get_wifi_adapter] = lambda: Adapter()
        try:
            files = [("files", ("a.pdf", b"x", "application/pdf"))]
            for _ in range(3):
                assert client.post("/upload", files=files).status_code == 400
            refused = client.post("/upload", files=files)
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)
        assert refused.status_code == 429
        assert refused.headers["Retry-After"] == "600"
        assert "Too many uploads from this phone" in refused.text
        assert "<form" in refused.text
        assert handled == [1, 1, 1]

    def test_storage_full_page(self, app_with):
        guard, _ = make_guard(free=100 * MB)
        client = app_with(guard)
        response = client.post("/upload", files=[("files", ("a.pdf", b"x", "application/pdf"))])
        assert response.status_code == 507
        assert STORAGE_FULL_MESSAGE.replace("'", "&#39;") in response.text

    def test_other_routes_are_not_limited(self, app_with):
        guard, _ = make_guard(free=0)
        client = app_with(guard)
        assert client.get("/upload").status_code == 200
        assert client.get("/health").status_code == 200
