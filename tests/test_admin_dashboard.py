"""
Integration tests for the Admin Dashboard process: the users table via
DatabaseManager, the CLI's account-creation/reset functions, /login + the
protected /me endpoint on admin_dashboard.main:app (issue #13), and session
sliding-timeout, lockout, and the login audit log (issue #14).

Follows the same TestClient + dependency-override pattern as
tests/test_webapp.py, but per issue #11's testing decisions, points get_db
at a real temporary SQLite file (seeded through models.init_db() and the
CLI's own functions) rather than an in-memory fake — auth/session logic is
exactly the kind of thing that should be exercised against the real schema,
through real HTTP requests, not mocked. Sliding-timeout and lockout expiry
are tested by backdating the relevant value directly (a mocked clock for
sessions, a past `locked_until` write for lockout), not by bypassing checks.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.auth import (
    FAILED_ATTEMPTS_LOCKOUT_THRESHOLD,
    SESSION_COOKIE_NAME,
    create_session_token,
    hash_password,
    verify_password,
)
from admin_dashboard.cli import create_account, reset_password
from admin_dashboard.dependencies import get_db
from database.db_manager import DatabaseManager
from database.models import init_db


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "dashboard_test.db")
    init_db(db_path)
    db = DatabaseManager(db_path=db_path)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(temp_db):
    """A TestClient wired to temp_db for the duration of the test, with the
    override cleaned up afterwards. A fresh client per test also avoids
    leaking session cookies between tests (TestClient persists cookies like
    a real browser session)."""
    app.dependency_overrides[get_db] = lambda: temp_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestPasswordHashing:
    def test_hash_is_not_the_plaintext_password(self):
        hashed = hash_password("correct horse battery staple")
        assert hashed != "correct horse battery staple"

    def test_verify_accepts_the_correct_password(self):
        hashed = hash_password("hunter2")
        assert verify_password("hunter2", hashed) is True

    def test_verify_rejects_a_wrong_password(self):
        hashed = hash_password("hunter2")
        assert verify_password("wrong", hashed) is False


class TestCLIAccountManagement:
    def test_create_account_stores_an_argon2_hash_not_plaintext(self, temp_db):
        assert create_account(temp_db, "alice", "s3cret!", "dev") is True

        row = temp_db.get_user_by_username("alice")
        assert row["role"] == "dev"
        assert row["password_hash"] != "s3cret!"
        assert row["password_hash"].startswith("$argon2id$")

    def test_create_account_rejects_a_duplicate_username(self, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        assert create_account(temp_db, "alice", "different", "admin") is False

    def test_reset_password_updates_an_existing_account(self, temp_db):
        create_account(temp_db, "alice", "old-password", "dev")

        assert reset_password(temp_db, "alice", "new-password") is True

        row = temp_db.get_user_by_username("alice")
        assert verify_password("new-password", row["password_hash"]) is True
        assert verify_password("old-password", row["password_hash"]) is False

    def test_reset_password_returns_false_for_an_unknown_account(self, temp_db):
        assert reset_password(temp_db, "nobody", "new-password") is False


class TestLogin:
    def test_correct_credentials_return_a_signed_session_cookie(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        response = client.post("/login", json={"username": "alice", "password": "s3cret!"})

        assert response.status_code == 200
        assert SESSION_COOKIE_NAME in response.cookies

    def test_wrong_password_is_rejected(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        response = client.post("/login", json={"username": "alice", "password": "wrong"})

        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in response.cookies

    def test_unknown_username_is_rejected(self, client):
        response = client.post("/login", json={"username": "ghost", "password": "whatever"})

        assert response.status_code == 401


class TestProtectedEndpoint:
    def test_unreachable_without_a_session_cookie(self, client):
        response = client.get("/me")

        assert response.status_code == 401

    def test_unreachable_with_a_tampered_cookie(self, client):
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-valid-token")

        response = client.get("/me")

        assert response.status_code == 401

    def test_reachable_with_a_valid_cookie_and_reflects_username_and_role(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        login_response = client.post("/login", json={"username": "alice", "password": "s3cret!"})

        me_response = client.get("/me")

        assert login_response.status_code == 200
        assert me_response.status_code == 200
        assert me_response.json() == {"username": "alice", "role": "dev"}

    def test_reflects_the_admin_role_too(self, client, temp_db):
        create_account(temp_db, "bob", "s3cret!", "admin")
        client.post("/login", json={"username": "bob", "password": "s3cret!"})

        response = client.get("/me")

        assert response.json() == {"username": "bob", "role": "admin"}


class TestAccountLockout:
    def test_five_consecutive_failures_lock_the_account(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        for _ in range(FAILED_ATTEMPTS_LOCKOUT_THRESHOLD):
            response = client.post("/login", json={"username": "alice", "password": "wrong"})
            assert response.status_code == 401

        row = temp_db.get_user_by_username("alice")
        assert row["locked_until"] is not None

    def test_locked_account_rejects_the_correct_password(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        for _ in range(FAILED_ATTEMPTS_LOCKOUT_THRESHOLD):
            client.post("/login", json={"username": "alice", "password": "wrong"})

        response = client.post("/login", json={"username": "alice", "password": "s3cret!"})

        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in response.cookies

    def test_fewer_than_five_failures_do_not_lock_the_account(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        for _ in range(FAILED_ATTEMPTS_LOCKOUT_THRESHOLD - 1):
            client.post("/login", json={"username": "alice", "password": "wrong"})

        response = client.post("/login", json={"username": "alice", "password": "s3cret!"})

        assert response.status_code == 200

    def test_successful_login_after_lockout_window_passes_resets_the_count(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        for _ in range(FAILED_ATTEMPTS_LOCKOUT_THRESHOLD):
            client.post("/login", json={"username": "alice", "password": "wrong"})
        # Backdate the lock into the past, as if the 15-minute window elapsed.
        temp_db.set_account_lock("alice", datetime.now() - timedelta(seconds=1))

        response = client.post("/login", json={"username": "alice", "password": "s3cret!"})

        assert response.status_code == 200
        row = temp_db.get_user_by_username("alice")
        assert row["failed_attempts"] == 0
        assert row["locked_until"] is None

    def test_a_further_failure_after_the_window_expires_relocks_the_account(self, client, temp_db):
        # Only a *successful* login resets the failed-attempt count (AC3),
        # so a wrong password after the window lapses re-locks immediately
        # rather than requiring a fresh run of 5 failures.
        create_account(temp_db, "alice", "s3cret!", "dev")
        for _ in range(FAILED_ATTEMPTS_LOCKOUT_THRESHOLD):
            client.post("/login", json={"username": "alice", "password": "wrong"})
        temp_db.set_account_lock("alice", datetime.now() - timedelta(seconds=1))

        response = client.post("/login", json={"username": "alice", "password": "wrong"})

        assert response.status_code == 401
        row = temp_db.get_user_by_username("alice")
        assert row["locked_until"] is not None
        assert datetime.fromisoformat(row["locked_until"]) > datetime.now()

    def test_unaffected_accounts_can_still_log_in(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        create_account(temp_db, "bob", "hunter2", "dev")
        for _ in range(FAILED_ATTEMPTS_LOCKOUT_THRESHOLD):
            client.post("/login", json={"username": "alice", "password": "wrong"})

        response = client.post("/login", json={"username": "bob", "password": "hunter2"})

        assert response.status_code == 200


class TestLoginAuditLog:
    def test_a_successful_login_is_logged(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        client.post("/login", json={"username": "alice", "password": "s3cret!"})

        rows = temp_db.get_login_log("alice")
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"
        assert rows[0]["success"] == 1
        assert rows[0]["timestamp"] is not None
        assert rows[0]["source_ip"] is not None

    def test_a_failed_login_is_logged(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        client.post("/login", json={"username": "alice", "password": "wrong"})

        rows = temp_db.get_login_log("alice")
        assert len(rows) == 1
        assert rows[0]["success"] == 0

    def test_an_unknown_username_is_still_logged(self, client, temp_db):
        client.post("/login", json={"username": "ghost", "password": "whatever"})

        rows = temp_db.get_login_log("ghost")
        assert len(rows) == 1
        assert rows[0]["success"] == 0

    def test_every_attempt_creates_its_own_row(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")

        client.post("/login", json={"username": "alice", "password": "wrong"})
        client.post("/login", json={"username": "alice", "password": "wrong"})
        client.post("/login", json={"username": "alice", "password": "s3cret!"})

        rows = temp_db.get_login_log("alice")
        assert [r["success"] for r in rows] == [0, 0, 1]


class TestSessionTimeout:
    def test_a_session_within_the_window_is_valid(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        stale_activity = (datetime.now() - timedelta(hours=1)).timestamp()
        client.cookies.set(
            SESSION_COOKIE_NAME, create_session_token("alice", "dev", last_activity=stale_activity)
        )

        response = client.get("/me")

        assert response.status_code == 200

    def test_a_session_idle_past_ten_hours_is_expired(self, client, temp_db):
        create_account(temp_db, "alice", "s3cret!", "dev")
        expired_activity = (datetime.now() - timedelta(hours=10, minutes=1)).timestamp()
        client.cookies.set(
            SESSION_COOKIE_NAME, create_session_token("alice", "dev", last_activity=expired_activity)
        )

        response = client.get("/me")

        assert response.status_code == 401

    def test_activity_resets_the_countdown(self, client, temp_db):
        from admin_dashboard.auth import read_session_token

        create_account(temp_db, "alice", "s3cret!", "dev")
        stale_activity = (datetime.now() - timedelta(hours=9)).timestamp()
        client.cookies.set(
            SESSION_COOKIE_NAME, create_session_token("alice", "dev", last_activity=stale_activity)
        )

        response = client.get("/me")

        assert response.status_code == 200
        refreshed_payload = read_session_token(response.cookies[SESSION_COOKIE_NAME])
        assert refreshed_payload["last_activity"] > stale_activity
