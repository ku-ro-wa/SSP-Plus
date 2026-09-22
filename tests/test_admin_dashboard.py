"""
Integration tests for the Admin Dashboard process (issue #13): the users
table via DatabaseManager, the CLI's account-creation/reset functions, and
/login + the protected /me endpoint on admin_dashboard.main:app.

Follows the same TestClient + dependency-override pattern as
tests/test_webapp.py, but per issue #11's testing decisions, points get_db
at a real temporary SQLite file (seeded through models.init_db() and the
CLI's own functions) rather than an in-memory fake — auth/session logic is
exactly the kind of thing that should be exercised against the real schema,
through real HTTP requests, not mocked.
"""
import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.auth import SESSION_COOKIE_NAME, hash_password, verify_password
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
