"""/kiosk and /logs on the Admin Dashboard (docs/adr/0005, release 1): read-only
pages over the shared DB, reachable by both roles, never writing."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from admin_dashboard.kiosk_overview import describe_last_seen
from database.db_manager import DatabaseManager
from database.models import init_db
from managers.kiosk_status import SETTING_LAST_SEEN, SETTING_QR_STATUS, heartbeat_timestamp


@pytest.fixture
def temp_db(tmp_path):
    path = str(tmp_path / "kiosk_pages.db")
    init_db(path)
    db = DatabaseManager(db_path=path)
    yield db
    db.close()


@pytest.fixture
def client(temp_db):
    app.dependency_overrides[get_db] = lambda: temp_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _login(client, db, role="operator"):
    create_account(db, "u", "s3cret!", role)
    client.post("/login", json={"username": "u", "password": "s3cret!"})


class TestLastSeen:
    NOW = datetime(2026, 10, 30, 12, 0, 0)

    def test_recent_heartbeat_is_online(self):
        online, text = describe_last_seen((self.NOW - timedelta(seconds=30)).isoformat(), self.NOW)
        assert online and text == "online, 30 s ago"

    def test_old_heartbeat_is_offline_since(self):
        online, text = describe_last_seen(datetime(2026, 10, 30, 9, 12).isoformat(), self.NOW)
        assert not online and text == "offline since 09:12"

    def test_missing_or_garbled_is_never_seen(self):
        assert describe_last_seen(None, self.NOW) == (False, "never seen")
        assert describe_last_seen("garbage", self.NOW) == (False, "never seen")


class TestKioskPage:
    def test_requires_login(self, client):
        assert client.get("/kiosk", follow_redirects=False).status_code == 303
        assert client.get("/kiosk/data").status_code == 401
        assert client.get("/logs", follow_redirects=False).status_code == 303

    def test_shows_supplies_reader_and_heartbeat(self, client, temp_db):
        temp_db.update_setting(SETTING_LAST_SEEN, heartbeat_timestamp())
        temp_db.update_setting(SETTING_QR_STATUS, "Connected")
        temp_db.update_paper_count(42)
        temp_db.update_cmyk_ink_levels(80, 60, 5, 0)
        _login(client, temp_db)

        data = client.get("/kiosk/data").json()

        assert data["online"] is True
        assert data["qr_reader"] == "Connected"
        assert data["paper"] == {"count": 42, "low": False}
        tanks = {t["name"]: t for t in data["ink"]["tanks"]}
        assert tanks["cyan"]["low"] is False
        assert tanks["yellow"]["low"] is True and tanks["yellow"]["empty"] is False
        assert tanks["black"]["empty"] is True

    def test_low_paper_is_flagged(self, client, temp_db):
        temp_db.update_paper_count(3)
        _login(client, temp_db)
        assert client.get("/kiosk/data").json()["paper"]["low"] is True

    def test_only_unresolved_errors_are_listed(self, client, temp_db):
        temp_db.log_error("Printer", "paper jam", "thank_you")
        temp_db.log_error("Modem", "no signal", "admin")
        temp_db.conn.execute("UPDATE error_log SET resolved = 1 WHERE error_type = 'Modem'")
        temp_db.conn.commit()
        _login(client, temp_db)

        data = client.get("/kiosk/data").json()

        assert data["error_total"] == 1
        assert data["errors"][0]["error_type"] == "Printer"

    def test_page_renders_for_a_fresh_db_and_both_roles(self, client, temp_db):
        _login(client, temp_db, role="admin")
        response = client.get("/kiosk")
        assert response.status_code == 200
        assert "never seen" in response.text
        assert 'id="ink-cyan"' in response.text  # init_db seeds full tanks


class TestLogsPage:
    def test_renders_all_three_tables(self, client, temp_db):
        temp_db.log_error("Printer", "paper jam", "thank_you")
        _login(client, temp_db)

        response = client.get("/logs")

        assert response.status_code == 200
        for anchor in ('id="transactions"', 'id="cash"', 'id="error-log"'):
            assert anchor in response.text
        assert "paper jam" in response.text
