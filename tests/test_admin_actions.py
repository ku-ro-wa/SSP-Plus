"""
admin_actions (issue #134): every operator change writes exactly one audit row,
from the touchscreen's admin models and through the Dashboard's real HTTP routes,
and both views list the same rows. No Qt event loop.
"""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from database.db_manager import DatabaseManager
from database.models import ensure_admin_actions_table, init_db
from managers import admin_actions
from managers.settings_catalog import get_setting_def
from managers.admin_actions import PAGE_SIZE, record_action, record_setting_changes


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "actions.db")
    init_db(path)
    return path


@pytest.fixture
def db(db_path):
    manager = DatabaseManager(db_path=db_path)
    yield manager
    manager.close()


def rows(db):
    found, _ = db.get_admin_action_page(1000)
    return [dict(r) for r in found]


# ---------------------------------------------------------------- the helper

class TestRecordAction:
    def test_writes_one_row_with_who_where_and_values(self, db):
        assert record_action(db, "paper", 40, 100, actor="sam", where="dashboard", ip="10.0.0.5") is True
        (row,) = rows(db)
        assert (row["actor"], row["location"], row["source_ip"]) == ("sam", "dashboard", "10.0.0.5")
        assert (row["action"], row["old_value"], row["new_value"]) == ("paper", "40", "100")
        assert row["timestamp"]

    def test_unchanged_value_writes_nothing(self, db):
        assert record_action(db, "paper", 100, "100", actor="kiosk", where="touchscreen") is False
        assert rows(db) == []

    def test_failed_write_is_logged_and_swallowed(self, monkeypatch):
        logged = []
        monkeypatch.setattr(admin_actions, "log_error", lambda *a, **k: logged.append(a))
        broken = MagicMock()
        broken.record_admin_action.side_effect = RuntimeError("boom")
        assert record_action(broken, "paper", 1, 2, actor="kiosk", where="touchscreen") is False
        assert len(logged) == 1

    def test_setting_changes_one_row_per_changed_key(self, db):
        n = record_setting_changes(db, {"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4},
                                   actor="kiosk", where="touchscreen")
        assert n == 2
        assert sorted(r["action"] for r in rows(db)) == ["setting:b", "setting:c"]


def test_migration_adds_the_table_to_an_older_database(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    ensure_admin_actions_table(conn)
    ensure_admin_actions_table(conn)  # idempotent
    assert conn.execute("SELECT COUNT(*) FROM admin_actions").fetchone()[0] == 0


# --------------------------------------------------------- touchscreen models

@pytest.fixture
def admin(db_path):
    from screens.admin import model as admin_model
    with patch.object(admin_model, "DatabaseManager", lambda: DatabaseManager(db_path=db_path)), \
            patch.object(admin_model, "get_sms_manager", lambda: MagicMock()):
        m = admin_model.AdminModel()
    return m


def actions(admin):
    return [(r["action"], r["old_value"], r["new_value"]) for r in reversed(rows(admin.db_manager))]


class TestTouchscreenPaper:
    def test_every_paper_edit_writes_one_row(self, admin):
        admin.db_manager.update_setting("paper_count", 40)
        admin.reset_paper_count()
        admin.decrease_paper_count()
        admin.increase_paper_count()
        admin.update_paper_count_from_string("55")
        assert actions(admin) == [
            ("paper", "40", "100"), ("paper", "100", "99"),
            ("paper", "99", "100"), ("paper", "100", "55"),
        ]
        assert all(r["actor"] == "kiosk" and r["location"] == "touchscreen" and r["source_ip"] is None
                   for r in rows(admin.db_manager))

    def test_saving_the_same_count_or_a_failed_edit_writes_nothing(self, admin):
        admin.update_paper_count_from_string("100")
        admin.update_paper_count_from_string("500")  # out of range
        admin.update_paper_count_from_string("x")
        assert actions(admin) == []

    def test_a_print_is_not_an_operator_action(self, admin):
        admin.decrement_paper_count(3)
        admin.mark_paper_empty()
        assert actions(admin) == []


class TestTouchscreenCoins:
    def test_set_each_denomination_writes_one_row(self, admin):
        admin.update_coin_1_count("30")
        admin.update_coin_5_count("12")
        admin.increase_coin_1_count()
        admin.decrease_coin_5_count()
        assert actions(admin) == [
            ("coins_1", "0", "30"), ("coins_5", "0", "12"),
            ("coins_1", "30", "31"), ("coins_5", "12", "11"),
        ]

    def test_refill_all_writes_a_row_per_hopper(self, admin):
        admin.reset_coin_counts()
        assert actions(admin) == [("coins_1", "0", "100"), ("coins_5", "0", "50")]

    def test_dispensing_change_is_not_an_operator_action(self, admin):
        admin.reset_coin_counts()
        before = len(actions(admin))
        assert admin.decrement_coins(2, 1) is True
        assert len(actions(admin)) == before


class TestTouchscreenInk:
    def test_set_and_refill(self, admin):
        admin.update_cmyk_levels(80, 60, 5, 0)
        admin.reset_cmyk_levels()
        assert actions(admin) == [
            ("ink", "C 100% M 100% Y 100% K 100%", "C 80% M 60% Y 5% K 0%"),
            ("ink", "C 80% M 60% Y 5% K 0%", "C 100% M 100% Y 100% K 100%"),
        ]

    def test_invalid_levels_write_nothing(self, admin):
        admin.update_cmyk_levels(101, 0, 0, 0)
        assert actions(admin) == []


class TestTouchscreenCollectCash:
    def test_one_row_with_the_counted_total(self, admin):
        admin.reset_coin_counts()  # 100 x ₱1 + 50 x ₱5 = ₱350
        before = len(actions(admin))
        assert admin.collect_cash() is True
        action, old, new = actions(admin)[before:][0]
        assert action == "collect_cash" and old == "₱350 counted" and new.startswith("collection #")
        assert len(actions(admin)) == before + 1


class TestTouchscreenSettings:
    def test_save_writes_one_row_per_changed_key_only(self, db):
        from screens.settings.model import SettingsModel
        model = SettingsModel(db)
        assert model.save({"max_change_limit": "60", "low_change_warning_threshold": "20"}) == {}
        (row,) = rows(db)
        assert (row["action"], row["new_value"], row["actor"]) == ("setting:max_change_limit", "60", "kiosk")

    def test_refused_save_writes_nothing(self, db):
        from screens.settings.model import SettingsModel
        errors = SettingsModel(db).save({"max_change_limit": "-5", "voucher_expiry_days": "10"})
        assert errors and rows(db) == []


# ------------------------------------------------------------------ dashboard

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, db, role="admin"):
    create_account(db, "sam", "s3cret!", role)
    client.post("/login", json={"username": "sam", "password": "s3cret!"})


class TestDashboardWrites:
    def test_paper_reset_writes_one_row_with_user_and_ip(self, client, db):
        db.update_setting("paper_count", 12)
        login(client, db)
        assert client.post("/paper-reset").status_code == 200
        (row,) = rows(db)
        assert (row["actor"], row["location"], row["action"]) == ("sam", "dashboard", "paper_reset")
        assert (row["old_value"], row["new_value"]) == ("12", "100")
        assert row["source_ip"] == "testclient"

    def test_settings_save_writes_one_row_per_changed_key(self, client, db):
        login(client, db)
        r = client.post("/settings", json={"values": {"max_change_limit": 70, "low_change_warning_threshold": 20}})
        assert r.status_code == 200
        (row,) = rows(db)
        default = str(get_setting_def("max_change_limit").default)
        assert (row["action"], row["old_value"], row["new_value"]) == ("setting:max_change_limit", default, "70")
        assert row["actor"] == "sam" and row["location"] == "dashboard"

    def test_refused_and_forbidden_writes_leave_no_row(self, client, db):
        login(client, db)
        assert client.post("/settings", json={"values": {"max_change_limit": -1}}).status_code == 422
        assert rows(db) == []
        client.cookies.clear()
        create_account(db, "olly", "s3cret!", "operator")
        client.post("/login", json={"username": "olly", "password": "s3cret!"})
        assert client.post("/paper-reset").status_code == 403
        assert client.post("/settings", json={"values": {"max_change_limit": 70}}).status_code == 403
        assert rows(db) == []


# ------------------------------------------------------- both views, same rows

def _seed(db, n):
    for i in range(n):
        record_action(db, "paper", i, i + 1, actor="kiosk", where="touchscreen")


class TestBothViewsShowTheSameRows:
    def test_logs_and_data_viewer_list_identical_rows_and_pages(self, client, db):
        from screens.data_viewer.model import DataViewerModel
        _seed(db, PAGE_SIZE + 5)
        login(client, db, "operator")

        viewer = DataViewerModel(db)
        seen = []
        viewer.admin_actions_loaded.connect(lambda r, p, n: seen.append(([dict(x) for x in r], p, n)))

        for page in (1, 2):
            dash = client.get(f"/logs/data?act_page={page}").json()["actions"]
            viewer.load_admin_actions(page)
            viewer_rows, vpage, vpages = seen[-1]
            assert [r["id"] for r in dash["rows"]] == [r["id"] for r in viewer_rows]
            assert (dash["page"], dash["pages"]) == (vpage, vpages) == (page, 2)
        assert len(dash["rows"]) == 5  # newest first, last page is the remainder

    def test_next_and_previous_pages_clamp(self, db):
        from screens.data_viewer.model import DataViewerModel
        _seed(db, PAGE_SIZE + 1)
        viewer = DataViewerModel(db)
        viewer.load_admin_actions(1)
        viewer.next_actions_page()
        viewer.next_actions_page()
        assert viewer.actions_page == 2
        viewer.previous_actions_page()
        viewer.previous_actions_page()
        assert viewer.actions_page == 1

    def test_logs_page_renders_the_section(self, client, db):
        record_action(db, "ink", "a", "b", actor="sam", where="dashboard", ip="10.1.1.1")
        login(client, db, "operator")
        html = client.get("/logs").text
        assert 'id="admin-actions"' in html and "dashboard (10.1.1.1)" in html

    def test_empty_trail_renders(self, client, db):
        login(client, db, "operator")
        assert "No admin actions." in client.get("/logs").text
