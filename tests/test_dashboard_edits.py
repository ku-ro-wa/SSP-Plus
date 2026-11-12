"""
Edits from the Admin Dashboard's /kiosk (issue #135): paper, coins, ink and Collect
cash, `admin` only, through the same managers/inventory_edits.py the touchscreen
uses. Real HTTP requests against the real app and a temp SQLite file.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from database.db_manager import DatabaseManager
from database.models import init_db


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "edits.db")
    init_db(path)
    return path


@pytest.fixture
def db(db_path):
    manager = DatabaseManager(db_path=db_path)
    yield manager
    manager.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, db, role="admin", name="sam"):
    client.cookies.clear()
    create_account(db, name, "s3cret!", role)
    client.post("/login", json={"username": name, "password": "s3cret!"})


def audit(db):
    rows, _ = db.get_admin_action_page(100)
    return [(r["action"], r["old_value"], r["new_value"]) for r in reversed(rows)]


def coins(db):
    return {int(i["denomination"]): i["count"] for i in db.get_cash_inventory() if i["type"] == "coin"}


# (path, body) of every edit, with a value the touchscreen would also accept.
EDITS = [
    ("/kiosk/paper", {"count": 40}),
    ("/kiosk/paper/refill", {}),
    ("/kiosk/coins", {"peso_1": 30}),
    ("/kiosk/coins/refill", {}),
    ("/kiosk/ink", {"levels": {"cyan": 50, "magenta": 50, "yellow": 50, "black": 50}}),
    ("/kiosk/ink/refill", {}),
    ("/kiosk/collect-cash", {}),
]


class TestWhoMayEdit:
    @pytest.mark.parametrize("path,body", EDITS)
    def test_unauthenticated_gets_401(self, client, db, path, body):
        assert client.post(path, json=body).status_code == 401
        assert audit(db) == []

    @pytest.mark.parametrize("path,body", EDITS)
    def test_operator_gets_403_and_nothing_changes(self, client, db, path, body):
        db.update_setting("paper_count", 77)
        login(client, db, "operator")
        assert client.post(path, json=body).status_code == 403
        assert audit(db) == [] and db.get_setting("paper_count") == 77

    def test_preview_is_admin_only(self, client, db):
        assert client.get("/kiosk/collect-cash/preview").status_code == 401
        login(client, db, "operator")
        assert client.get("/kiosk/collect-cash/preview").status_code == 403

    def test_page_shows_controls_to_admin_only(self, client, db):
        login(client, db, "operator")
        html = client.get("/kiosk").text
        assert 'data-edit="paper"' not in html and "collect-cash-button" not in html
        assert 'id="paper-count"' in html  # still sees the values
        login(client, db, "admin", "ann")
        html = client.get("/kiosk").text
        for marker in ('data-edit="paper"', 'data-edit="coins"', 'data-edit="ink"', "collect-cash-button"):
            assert marker in html


class TestPaper:
    def test_set_and_refill_each_write_one_row(self, client, db):
        db.update_setting("paper_count", 10)
        login(client, db)
        assert client.post("/kiosk/paper", json={"count": "42"}).json() == {"paper_count": 42}
        assert client.post("/kiosk/paper/refill").json() == {"paper_count": 100}
        assert db.get_setting("paper_count") == 100
        assert audit(db) == [("paper", "10", "42"), ("paper", "42", "100")]
        row = db.get_admin_action_page(1)[0][0]
        assert (row["actor"], row["location"], row["source_ip"]) == ("sam", "dashboard", "testclient")

    @pytest.mark.parametrize("bad", [-1, 101, "x", "", 2.5, None, True])
    def test_out_of_range_or_garbage_is_refused(self, client, db, bad):
        db.update_setting("paper_count", 10)
        login(client, db)
        r = client.post("/kiosk/paper", json={"count": bad})
        assert r.status_code == 422 and r.json()["error"]
        assert db.get_setting("paper_count") == 10 and audit(db) == []

    def test_same_value_writes_no_row(self, client, db):
        db.update_setting("paper_count", 55)
        login(client, db)
        assert client.post("/kiosk/paper", json={"count": 55}).status_code == 200
        assert audit(db) == []


class TestCoins:
    def test_set_one_or_both_hoppers(self, client, db):
        login(client, db)
        r = client.post("/kiosk/coins", json={"peso_1": 30})
        assert r.json() == {"peso_1": 30, "peso_5": 0}
        assert client.post("/kiosk/coins", json={"peso_1": "31", "peso_5": 12}).json() == {"peso_1": 31, "peso_5": 12}
        assert audit(db) == [("coins_1", "0", "30"), ("coins_1", "30", "31"), ("coins_5", "0", "12")]

    def test_refill_all(self, client, db):
        login(client, db)
        assert client.post("/kiosk/coins/refill").json() == {"peso_1": 100, "peso_5": 50}
        assert coins(db) == {1: 100, 5: 50}
        assert audit(db) == [("coins_1", "0", "100"), ("coins_5", "0", "50")]

    @pytest.mark.parametrize("body", [{"peso_1": -1}, {"peso_5": 1001}, {"peso_1": "x"}, {}, {"peso_1": 5, "peso_5": "no"}])
    def test_refused_edit_writes_neither_hopper(self, client, db, body):
        login(client, db)
        assert client.post("/kiosk/coins", json=body).status_code == 422
        assert coins(db) in ({}, {1: 0, 5: 0}) and audit(db) == []


class TestInk:
    LEVELS = {"cyan": 80, "magenta": "60.5", "yellow": 5, "black": 0}

    def test_set_and_refill(self, client, db):
        login(client, db)
        assert client.post("/kiosk/ink", json={"levels": self.LEVELS}).json()["levels"]["magenta"] == 60.5
        assert client.post("/kiosk/ink/refill").status_code == 200
        levels = db.get_cmyk_ink_levels()
        assert (levels["cyan"], levels["black"]) == (100.0, 100.0)
        assert audit(db) == [
            ("ink", "C 100% M 100% Y 100% K 100%", "C 80% M 60.5% Y 5% K 0%"),
            ("ink", "C 80% M 60.5% Y 5% K 0%", "C 100% M 100% Y 100% K 100%"),
        ]

    @pytest.mark.parametrize("levels", [
        {"cyan": 101, "magenta": 0, "yellow": 0, "black": 0},
        {"cyan": -1, "magenta": 0, "yellow": 0, "black": 0},
        {"cyan": "x", "magenta": 0, "yellow": 0, "black": 0},
        {"cyan": 5},
    ])
    def test_refused_levels_change_nothing(self, client, db, levels):
        login(client, db)
        assert client.post("/kiosk/ink", json={"levels": levels}).status_code == 422
        assert db.get_cmyk_ink_levels()["cyan"] == 100.0 and audit(db) == []


class TestCollectCash:
    def stock(self, db):
        db.update_cash_inventory(1, 100, "coin")
        db.update_cash_inventory(5, 50, "coin")

    def test_preview_matches_the_touchscreens(self, client, db):
        self.stock(db)
        login(client, db)
        assert client.get("/kiosk/collect-cash/preview").json() == db.get_collection_preview()
        assert db.get_collection_preview()["total"] == 350

    def test_collect_records_zeroes_and_writes_one_row(self, client, db):
        self.stock(db)
        login(client, db)
        r = client.post("/kiosk/collect-cash", json={"expected_total": 350})
        assert r.status_code == 200
        assert coins(db) == {1: 0, 5: 0}
        assert audit(db) == [("collect_cash", "₱350 counted", f"collection #{r.json()['collection_id']}")]
        assert db.conn.execute("SELECT COUNT(*) AS n FROM cash_collections").fetchone()["n"] == 1

    def test_counts_moved_since_the_preview_collects_nothing(self, client, db):
        self.stock(db)
        login(client, db)
        db.update_cash_inventory(1, 90, "coin")  # a payment landed after the operator looked
        r = client.post("/kiosk/collect-cash", json={"expected_total": 350})
        assert r.status_code == 409 and r.json()["preview"]["total"] == 340
        assert coins(db) == {1: 90, 5: 50} and audit(db) == []


class TestKioskNextPrintDoesNotUndoARemoteEdit:
    def test_dashboard_paper_edit_survives_the_next_print(self, client, db, db_path):
        from screens.admin import model as admin_model
        with patch.object(admin_model, "DatabaseManager", lambda: DatabaseManager(db_path=db_path)), \
                patch.object(admin_model, "get_sms_manager", lambda: MagicMock()):
            kiosk = admin_model.AdminModel()
        db.update_setting("paper_count", 20)
        kiosk.load_paper_count()  # the kiosk has 20 in memory

        login(client, db)
        client.post("/kiosk/paper", json={"count": 90})
        assert kiosk.decrement_paper_count(5) is True

        assert db.get_setting("paper_count") == 85
