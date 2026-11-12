"""/kiosk and /logs on the Admin Dashboard (docs/adr/0005, release 1): read-only
pages over the shared DB, reachable by both roles, never writing."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from admin_dashboard.kiosk_overview import ERRORS_SHOWN, ONLINE_WITHIN_SECONDS, describe_last_seen
from admin_dashboard.routers.kiosk import PAGE_SIZE
from admin_dashboard.templating import templates
from managers.supply_levels import COIN_CRIT, COIN_WARN, INK_CRIT, INK_WARN, PAPER_CRIT, PAPER_WARN, severity
from database.db_manager import DatabaseManager
from database.models import init_db
from managers.kiosk_status import (SETTING_LAST_SEEN, SETTING_QR_STATUS, heartbeat_timestamp,
                                  write_printer_status)


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


def _set_coins(db, peso_1, peso_5):
    for denomination, count in ((1.0, peso_1), (5.0, peso_5)):
        db.conn.execute(
            "INSERT OR REPLACE INTO cash_inventory (denomination, count, type, last_updated)"
            " VALUES (?, ?, 'coin', '2026-10-01 10:00:00')", (denomination, count))
    db.conn.commit()


class TestLastSeen:
    NOW = datetime(2026, 10, 30, 12, 0, 0)

    def test_recent_heartbeat_is_online(self):
        online, text = describe_last_seen((self.NOW - timedelta(seconds=30)).isoformat(), self.NOW)
        assert online and text == "online, 30 s ago"

    def test_old_heartbeat_is_offline_since(self):
        online, text = describe_last_seen(datetime(2026, 10, 30, 9, 12).isoformat(), self.NOW)
        assert not online and text == "offline since 09:12"

    def test_online_boundary(self):
        at = (self.NOW - timedelta(seconds=ONLINE_WITHIN_SECONDS)).isoformat()
        past = (self.NOW - timedelta(seconds=ONLINE_WITHIN_SECONDS + 1)).isoformat()
        assert describe_last_seen(at, self.NOW)[0] is True
        assert describe_last_seen(past, self.NOW)[0] is False

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
        assert data["paper"] == {"count": 42, "band": "warn"}
        tanks = {t["name"]: t for t in data["ink"]["tanks"]}
        assert tanks["cyan"]["band"] == "ok"
        assert tanks["yellow"]["band"] == "crit" and tanks["yellow"]["empty"] is False
        assert tanks["black"]["empty"] is True

    def test_shows_stored_printer_status(self, client, temp_db):
        write_printer_status(temp_db, "Paper jam", "error", datetime(2026, 1, 2, 3, 4, 5))
        _login(client, temp_db)

        printer = client.get("/kiosk/data").json()["printer"]
        assert printer["text"] == "Paper jam"
        assert printer["level"] == "error"
        assert printer["as_of"].endswith("03:04")

        html = client.get("/kiosk").text
        assert 'id="printer" class="bad">Paper jam' in html
        assert "as of" in html

    def test_printer_warning_and_success_colours(self, client, temp_db):
        _login(client, temp_db)
        write_printer_status(temp_db, "Paper low", "warning")
        assert 'id="printer" class="warn">Paper low' in client.get("/kiosk").text
        write_printer_status(temp_db, "Ready", "success")
        assert 'id="printer" class="ok">Ready' in client.get("/kiosk").text

    def test_no_printer_status_recorded_yet(self, client, temp_db):
        _login(client, temp_db)
        assert client.get("/kiosk/data").json()["printer"] is None
        r = client.get("/kiosk")
        assert r.status_code == 200
        assert 'id="printer">Unknown' in r.text

    def test_paper_and_coin_bands_use_the_shared_thresholds(self, client, temp_db):
        temp_db.update_paper_count(PAPER_CRIT)
        _set_coins(temp_db, COIN_WARN, COIN_WARN + 1)
        _login(client, temp_db)

        data = client.get("/kiosk/data").json()

        assert data["paper"]["band"] == "crit"
        assert data["coins"]["peso_1_band"] == "warn"
        assert data["coins"]["peso_5_band"] == "ok"

    def test_severity_edges(self):
        assert severity(PAPER_WARN, PAPER_WARN, PAPER_CRIT) == "warn"
        assert severity(PAPER_WARN + 1, PAPER_WARN, PAPER_CRIT) == "ok"
        assert severity(INK_CRIT, INK_WARN, INK_CRIT) == "crit"

    def test_unresolved_errors_are_capped_newest_first(self, client, temp_db):
        for i in range(ERRORS_SHOWN + 5):
            temp_db.log_error("Printer", f"err {i}", "x")
        _login(client, temp_db)

        data = client.get("/kiosk/data").json()

        assert data["error_total"] == ERRORS_SHOWN + 5
        assert len(data["errors"]) == ERRORS_SHOWN
        assert data["errors"][0]["error_message"] == f"err {ERRORS_SHOWN + 4}"

    def test_header_shows_kiosk_id_and_nav(self, client, temp_db, monkeypatch):
        monkeypatch.setitem(templates.env.globals, "kiosk_id", "KSK-7")
        _login(client, temp_db)
        text = client.get("/kiosk").text
        assert "KSK-7" in text
        assert 'href="/accounting"' in text and 'href="/logs"' in text
        for anchor in ("status", "paper", "coins", "ink", "errors"):
            assert f'id="{anchor}"' in text

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


def _add_transactions(db, n):
    for i in range(n):
        db.conn.execute(
            "INSERT INTO transactions (timestamp, file_name, pages, copies, color_mode, total_cost,"
            " amount_paid, change_given, status, source) VALUES (?, ?, 1, 1, 'BW', 5, 5, 0, 'completed', 'usb')",
            (f"2026-10-01 10:{i // 60:02d}:{i % 60:02d}", f"file{i}.pdf"),
        )
    db.conn.commit()


class TestLogsPagination:
    def test_first_page_is_newest_and_capped(self, client, temp_db):
        _add_transactions(temp_db, PAGE_SIZE + 5)
        _login(client, temp_db)

        data = client.get("/logs/data").json()["transactions"]

        assert len(data["rows"]) == PAGE_SIZE
        assert data["total"] == PAGE_SIZE + 5 and data["pages"] == 2
        assert data["rows"][0]["file_name"] == f"file{PAGE_SIZE + 4}.pdf"
        assert data["rows"][0]["source"] == "usb"

    def test_page_two_has_the_next_rows(self, client, temp_db):
        _add_transactions(temp_db, PAGE_SIZE + 5)
        _login(client, temp_db)

        data = client.get("/logs/data?tx_page=2").json()["transactions"]

        assert [r["file_name"] for r in data["rows"]] == [f"file{i}.pdf" for i in range(4, -1, -1)]

    def test_out_of_range_page_is_empty_not_an_error(self, client, temp_db):
        _add_transactions(temp_db, 3)
        temp_db.log_error("Printer", "jam", "x")
        _login(client, temp_db)

        data = client.get("/logs/data?tx_page=99&err_page=99").json()

        assert data["transactions"]["rows"] == [] and data["errors"]["rows"] == []
        assert client.get("/logs?tx_page=99&err_page=99").status_code == 200

    def test_errors_paginate_and_show_resolved(self, client, temp_db):
        for i in range(PAGE_SIZE + 1):
            temp_db.log_error("Printer", f"err {i}", "x")
        temp_db.conn.execute("UPDATE error_log SET resolved = 1 WHERE error_message = 'err 0'")
        temp_db.conn.commit()
        _login(client, temp_db)

        page2 = client.get("/logs/data?err_page=2").json()["errors"]

        assert len(page2["rows"]) == 1 and page2["rows"][0]["resolved"] == 1
        assert "Older" in client.get("/logs").text

    def test_json_requires_login_and_both_roles_read(self, client, temp_db):
        assert client.get("/logs/data").status_code == 401
        _set_coins(temp_db, 10, 10)
        _login(client, temp_db, role="operator")
        data = client.get("/logs/data").json()
        assert {d["denomination"] for d in data["cash"]} >= {1.0, 5.0}
