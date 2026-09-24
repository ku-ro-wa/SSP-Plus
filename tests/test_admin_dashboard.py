"""
Integration tests for the Admin Dashboard process: the users table via
DatabaseManager, the CLI's account-creation/reset functions, /login + the
protected /me endpoint on admin_dashboard.main:app (issue #13), session
sliding-timeout, lockout, and the login audit log (issue #14), the
accounting aggregate endpoint + summary table (issue #15), the vendored
Chart.js asset (issue #16), the dev-only paper-count reset endpoint (issue
#17), and the SIM_MODE-gated demo/fixture seed script (issue #18).

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
from pathlib import Path

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
from admin_dashboard.dependencies import get_db, open_db
from admin_dashboard.routers.accounting import PAPER_FULL_COUNT
from admin_dashboard.seed_demo_data import FIXTURES, SIM_DB_PATH, seed, seed_transaction
from database.db_manager import SIM_DB_NAME, DatabaseManager
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


def _insert_transaction(db, source, total_cost, status="completed", timestamp=None):
    """Seed a transactions row directly against the real schema (per issue
    #11's testing decision for aggregate queries) via seed_demo_data's
    shared seed_transaction helper, since DatabaseManager.log_transaction
    doesn't populate `source` — that write path is unrelated to issue #15's
    read-side aggregate endpoint."""
    seed_transaction(db.conn, source, total_cost, status=status, timestamp=timestamp)
    db.conn.commit()


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
    def test_cli_uses_the_same_sim_mode_db_file_as_the_dashboard(self, monkeypatch):
        """Regression: the CLI used to always write to the real DB, so with
        SIM_MODE=true newly created accounts were invisible to /login."""
        monkeypatch.setenv("SIM_MODE", "true")
        pre_existing = SIM_DB_PATH.exists()

        db = open_db()
        try:
            assert Path(db.db_path).resolve() == SIM_DB_PATH.resolve()
        finally:
            db.close()
            if not pre_existing and SIM_DB_PATH.exists():
                SIM_DB_PATH.unlink()

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


class TestAccountingSummary:
    """DatabaseManager.get_accounting_summary (issue #15) — the query
    backing the /accounting/data endpoint."""

    def test_groups_revenue_and_transaction_count_by_source(self, temp_db):
        _insert_transaction(temp_db, "usb", 10.0)
        _insert_transaction(temp_db, "usb", 5.0)
        _insert_transaction(temp_db, "wifi", 20.0)
        _insert_transaction(temp_db, "email", 7.5)

        summary = {row["source"]: row for row in temp_db.get_accounting_summary()}

        assert summary["usb"]["revenue"] == 15.0
        assert summary["usb"]["transaction_count"] == 2
        assert summary["wifi"]["revenue"] == 20.0
        assert summary["wifi"]["transaction_count"] == 1
        assert summary["email"]["revenue"] == 7.5
        assert summary["email"]["transaction_count"] == 1

    def test_zero_fills_sources_with_no_transactions(self, temp_db):
        _insert_transaction(temp_db, "usb", 10.0)

        summary = {row["source"]: row for row in temp_db.get_accounting_summary()}

        assert set(summary.keys()) == {"usb", "wifi", "email", "scanner"}
        assert summary["email"]["revenue"] == 0
        assert summary["email"]["transaction_count"] == 0
        assert summary["scanner"]["revenue"] == 0
        assert summary["scanner"]["transaction_count"] == 0

    def test_excludes_non_completed_transactions(self, temp_db):
        _insert_transaction(temp_db, "usb", 10.0, status="cancelled_partial_payment")

        summary = {row["source"]: row for row in temp_db.get_accounting_summary()}

        assert summary["usb"]["revenue"] == 0
        assert summary["usb"]["transaction_count"] == 0

    def test_scopes_results_to_a_since_timestamp(self, temp_db):
        old = datetime.now() - timedelta(days=10)
        _insert_transaction(temp_db, "usb", 10.0, timestamp=old)
        _insert_transaction(temp_db, "usb", 5.0)

        summary = {
            row["source"]: row
            for row in temp_db.get_accounting_summary(since=datetime.now() - timedelta(days=1))
        }

        assert summary["usb"]["revenue"] == 5.0
        assert summary["usb"]["transaction_count"] == 1

    def test_a_photocopy_scanner_transaction_is_counted(self, temp_db):
        # Per CONTEXT.md's Photocopy term, a `scanner`-sourced row only
        # exists in `transactions` at all when the scan's destination was
        # print — scan-to-email/download never reach this table. So any
        # seeded `scanner` row here is, by construction, a Photocopy.
        _insert_transaction(temp_db, "scanner", 8.0)

        summary = {row["source"]: row for row in temp_db.get_accounting_summary()}

        assert summary["scanner"]["revenue"] == 8.0
        assert summary["scanner"]["transaction_count"] == 1


class TestAccountingEndpoints:
    """/accounting and /accounting/data (issue #15)."""

    def test_data_endpoint_requires_login(self, client):
        response = client.get("/accounting/data")

        assert response.status_code == 401

    def test_page_redirects_to_the_login_form_without_a_session(self, client):
        response = client.get("/accounting", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_page_redirects_to_the_login_form_with_an_expired_session(self, client):
        expired = create_session_token("alice", "dev", last_activity=0)
        client.cookies.set(SESSION_COOKIE_NAME, expired)

        response = client.get("/accounting", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_dev_role_can_view_the_data_endpoint_and_page(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        _insert_transaction(temp_db, "usb", 10.0)
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        data_response = client.get("/accounting/data?range=all")
        page_response = client.get("/accounting")

        assert data_response.status_code == 200
        sources = {row["source"]: row for row in data_response.json()["sources"]}
        assert sources["usb"]["revenue"] == 10.0
        assert page_response.status_code == 200
        assert "usb" in page_response.text

    def test_admin_role_can_view_the_data_endpoint_and_page(self, client, temp_db):
        create_account(temp_db, "admin1", "s3cret!", "admin")
        _insert_transaction(temp_db, "usb", 10.0)
        client.post("/login", json={"username": "admin1", "password": "s3cret!"})

        data_response = client.get("/accounting/data?range=all")
        page_response = client.get("/accounting")

        assert data_response.status_code == 200
        assert page_response.status_code == 200

    def test_time_filter_scopes_the_data_endpoint(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        old = datetime.now() - timedelta(days=40)
        _insert_transaction(temp_db, "usb", 10.0, timestamp=old)
        _insert_transaction(temp_db, "usb", 5.0)
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        month_response = client.get("/accounting/data?range=month")
        all_response = client.get("/accounting/data?range=all")

        month_sources = {row["source"]: row for row in month_response.json()["sources"]}
        all_sources = {row["source"]: row for row in all_response.json()["sources"]}
        assert month_sources["usb"]["revenue"] == 5.0
        assert all_sources["usb"]["revenue"] == 15.0

    def test_today_filter_excludes_transactions_from_a_prior_day(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        yesterday = datetime.now() - timedelta(days=1)
        _insert_transaction(temp_db, "usb", 10.0, timestamp=yesterday)
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        response = client.get("/accounting/data?range=today")

        sources = {row["source"]: row for row in response.json()["sources"]}
        assert sources["usb"]["revenue"] == 0


class TestChartAsset:
    """The vendored Chart.js bar chart on /accounting (issue #16)."""

    def test_chartjs_is_served_from_the_dashboards_own_static_files(self, client):
        response = client.get("/static/js/chart.umd.min.js")

        assert response.status_code == 200
        assert "Chart" in response.text

    def test_accounting_page_references_only_the_local_chart_asset(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        response = client.get("/accounting")

        assert 'src="/static/js/chart.umd.min.js"' in response.text
        # No CDN dependency (issue #16's AC) — nothing fetched from an
        # external host anywhere in the page.
        assert "cdn." not in response.text
        assert "http://" not in response.text
        assert "https://" not in response.text

    def test_accounting_page_embeds_the_initial_chart_data(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        _insert_transaction(temp_db, "usb", 10.0)
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        response = client.get("/accounting")

        assert '"source": "usb"' in response.text or '"source":"usb"' in response.text


class TestBrowserEntryPoints:
    """The browser-facing routes: / as the landing page and the GET /login
    sign-in form."""

    def test_root_redirects_to_accounting(self, client):
        response = client.get("/", follow_redirects=False)

        assert response.status_code in (302, 303, 307)
        assert response.headers["location"] == "/accounting"

    def test_login_form_is_served_without_a_session(self, client):
        response = client.get("/login")

        assert response.status_code == 200
        assert "<form" in response.text
        assert 'type="password"' in response.text

    def test_root_lands_on_accounting_once_logged_in(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        response = client.get("/")

        assert response.status_code == 200
        assert "Accounting" in response.text


class TestPaperReset:
    """The dev-only paper-count reset endpoint (issue #17)."""

    def test_dev_role_can_reset_the_paper_count(self, client, temp_db):
        create_account(temp_db, "dev1", "s3cret!", "dev")
        temp_db.update_paper_count(3)
        client.post("/login", json={"username": "dev1", "password": "s3cret!"})

        response = client.post("/paper-reset")

        assert response.status_code == 200
        assert response.json() == {"paper_count": PAPER_FULL_COUNT}
        assert temp_db.get_setting("paper_count", default=None) == PAPER_FULL_COUNT

    def test_admin_role_is_forbidden_and_paper_count_is_unchanged(self, client, temp_db):
        create_account(temp_db, "admin1", "s3cret!", "admin")
        temp_db.update_paper_count(3)
        client.post("/login", json={"username": "admin1", "password": "s3cret!"})

        response = client.post("/paper-reset")

        assert response.status_code == 403
        assert temp_db.get_setting("paper_count", default=None) == 3

    def test_unauthenticated_request_is_rejected_and_paper_count_is_unchanged(self, client, temp_db):
        temp_db.update_paper_count(3)

        response = client.post("/paper-reset")

        assert response.status_code == 401
        assert temp_db.get_setting("paper_count", default=None) == 3


class TestDemoSeedScript:
    """The SIM_MODE-gated demo/fixture seed script (issue #18)."""

    def test_seeds_a_file_distinct_from_the_real_database(self):
        assert SIM_DB_PATH.name != "ssp_database.db"
        assert SIM_DB_NAME != "ssp_database.db"

    def test_populates_all_four_sources(self, tmp_path):
        db_path = tmp_path / "demo.sim.db"

        seed(db_path)

        db = DatabaseManager(db_path=str(db_path))
        try:
            summary = {row["source"]: row for row in db.get_accounting_summary()}
        finally:
            db.close()
        assert set(summary.keys()) == {"usb", "wifi", "email", "scanner"}
        for source in ("usb", "wifi", "email", "scanner"):
            assert summary[source]["transaction_count"] > 0

    def test_fixtures_span_every_time_filter_distinctly(self, tmp_path):
        db_path = tmp_path / "demo.sim.db"

        seed(db_path)

        db = DatabaseManager(db_path=str(db_path))
        try:
            today = sum(row["revenue"] for row in db.get_accounting_summary(
                since=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)))
            week = sum(row["revenue"] for row in db.get_accounting_summary(
                since=datetime.now() - timedelta(days=7)))
            month = sum(row["revenue"] for row in db.get_accounting_summary(
                since=datetime.now() - timedelta(days=30)))
            all_time = sum(row["revenue"] for row in db.get_accounting_summary())
        finally:
            db.close()
        # Strictly increasing as the window widens — each filter shows a
        # different, non-empty total (issue #18's AC).
        assert 0 < today < week < month < all_time

    def test_never_writes_to_the_real_database_path(self, tmp_path):
        real_db_path = tmp_path / "ssp_database.db"
        demo_db_path = tmp_path / "demo.sim.db"

        seed(demo_db_path)

        assert not real_db_path.exists()

    def test_running_it_twice_appends_a_second_set_of_fixtures(self, tmp_path):
        # #18 doesn't ask for idempotency (unlike #12's schema migration) —
        # this just documents the actual behavior: init_db() is idempotent,
        # but seed()'s inserts are not, so a second run doubles the rows.
        db_path = tmp_path / "demo.sim.db"

        seed(db_path)
        seed(db_path)

        db = DatabaseManager(db_path=str(db_path))
        try:
            total_count = sum(row["transaction_count"] for row in db.get_accounting_summary())
        finally:
            db.close()
        assert total_count == 2 * len(FIXTURES)

    def test_main_refuses_to_run_when_sim_mode_is_not_enabled(self, monkeypatch):
        from admin_dashboard import seed_demo_data

        monkeypatch.setenv("SIM_MODE", "false")
        with pytest.raises(SystemExit):
            seed_demo_data.main()

    def test_get_db_reads_the_demo_file_when_sim_mode_is_enabled(self, monkeypatch):
        monkeypatch.setenv("SIM_MODE", "true")
        pre_existing = SIM_DB_PATH.exists()

        gen = get_db()
        db = next(gen)
        try:
            assert db.db_path.endswith(SIM_DB_NAME)
        finally:
            gen.close()
            if not pre_existing and SIM_DB_PATH.exists():
                SIM_DB_PATH.unlink()

    def test_accounting_page_visibly_shows_seeded_demo_data_in_sim_mode(self, monkeypatch):
        """AC4: 'With SIM_MODE=true, the dashboard reads from the seeded
        demo file and visibly displays the fixture data in the summary
        table/chart.' Driven through real HTTP with get_db left un-overridden
        (per issue #11's 'one seam, in-process HTTP' testing decision), the
        one test in this file that doesn't use the client/temp_db fixtures —
        it needs the app's real SIM_MODE-aware get_db, not the fixture
        override every other test relies on."""
        monkeypatch.setenv("SIM_MODE", "true")
        pre_existing = SIM_DB_PATH.exists()

        seed()
        seeded_db = DatabaseManager(db_path=str(SIM_DB_PATH))
        try:
            create_account(seeded_db, "simdemo", "s3cret!", "dev")
        finally:
            seeded_db.close()

        try:
            sim_client = TestClient(app)
            sim_client.post("/login", json={"username": "simdemo", "password": "s3cret!"})

            response = sim_client.get("/accounting")

            assert response.status_code == 200
            assert "usb" in response.text
        finally:
            if not pre_existing and SIM_DB_PATH.exists():
                SIM_DB_PATH.unlink()
