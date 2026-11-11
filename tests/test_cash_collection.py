"""
Cash collection (issue #110): Kiosk Admin records the counts and zeroes them,
cancelling writes nothing, and the Admin Dashboard lists collections read-only.
All against a temp SQLite file seeded through init_db().
"""
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from admin_dashboard.cli import create_account  # noqa: E402
from admin_dashboard.dependencies import get_db  # noqa: E402
from admin_dashboard.seed_demo_data import seed_transaction  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.payment_algorithm_manager import PaymentAlgorithmManager  # noqa: E402
from SSP.admin_dashboard.main import app  # noqa: E402
from screens.admin.controller import AdminController  # noqa: E402
from screens.admin.view import AdminScreenView  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "collect.db")
    init_db(path)
    return path


@pytest.fixture
def db(db_path):
    d = DatabaseManager(db_path=db_path)
    d.update_cash_inventory(1, 80, 'coin')
    d.update_cash_inventory(5, 30, 'coin')
    d.update_cash_inventory(20, 4, 'bill')
    d.update_cash_inventory(100, 2, 'bill')
    yield d
    d.close()


def _counts(db):
    return {(r['denomination'], r['type']): r['count'] for r in db.get_cash_inventory()}


def _tables(db):
    return (
        db.conn.execute("SELECT COUNT(*) AS n FROM cash_collections").fetchone()['n'],
        db.conn.execute("SELECT COUNT(*) AS n FROM cash_collection_items").fetchone()['n'],
    )


class TestRecordCollection:
    def test_records_one_collection_with_items_and_zeroes_inventory(self, db):
        collection_id = db.record_cash_collection()

        assert collection_id is not None
        (collection,) = db.get_cash_collections()
        assert collection['total'] == 80 + 30 * 5 + 4 * 20 + 2 * 100
        items = {(i['denomination'], i['type']): i['count'] for i in collection['items']}
        assert items == {(1.0, 'coin'): 80, (5.0, 'coin'): 30, (20.0, 'bill'): 4, (100.0, 'bill'): 2}
        assert set(_counts(db).values()) == {0}

    def test_missing_coin_rows_are_listed_as_zero(self, db_path):
        empty = DatabaseManager(db_path=db_path)
        preview = empty.get_collection_preview()
        assert [(i['denomination'], i['count']) for i in preview['items']] == [(1.0, 0), (5.0, 0)]
        assert preview['total'] == 0

    def test_database_error_rolls_everything_back(self, db):
        db.conn.execute("DROP TABLE cash_collection_items")
        db.conn.commit()

        assert db.record_cash_collection() is None

        assert _tables_count(db, "cash_collections") == 0
        assert _counts(db)[(1.0, 'coin')] == 80

    def test_newest_first(self, db):
        db.record_cash_collection()
        db.update_cash_inventory(1, 7, 'coin')
        second = db.record_cash_collection()

        assert db.get_cash_collections()[0]['id'] == second

    def test_low_change_banner_condition_holds_until_recount(self, db):
        db.record_cash_collection()
        algo = PaymentAlgorithmManager(db)
        assert algo.is_change_low()
        db.update_cash_inventory(1, 100, 'coin')
        db.update_cash_inventory(5, 50, 'coin')
        assert not PaymentAlgorithmManager(db).is_change_low()


def _tables_count(db, table):
    return db.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()['n']


class TestMigration:
    def test_fresh_database_has_the_tables(self, db_path):
        conn = sqlite3.connect(db_path)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"cash_collections", "cash_collection_items"} <= names

    def test_existing_database_migrates_without_touching_data(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TABLE cash_collections")
        conn.execute("DROP TABLE cash_collection_items")
        conn.execute("INSERT INTO cash_inventory VALUES (1, 42, 'coin', '2026-01-01')")
        conn.commit()
        conn.close()

        init_db(db_path)
        init_db(db_path)  # idempotent

        db = DatabaseManager(db_path=db_path)
        assert _counts(db)[(1.0, 'coin')] == 42
        assert db.get_cash_collections() == []


class TestKioskAdmin:
    @pytest.fixture
    def controller(self, qapp, db_path, db):
        from screens.admin import model as admin_model

        with patch.object(admin_model, "DatabaseManager", lambda: DatabaseManager(db_path=db_path)), \
                patch.object(admin_model, "get_sms_manager", lambda: MagicMock()):
            return AdminController(MagicMock())

    def test_confirm_collects_and_zeroes(self, controller, db):
        shown = {}

        def confirm(items, total):
            shown['items'], shown['total'] = items, total
            return True

        controller.view.confirm_collect_cash = confirm
        controller.view.collect_cash_clicked.emit()

        assert shown['total'] == 80 + 150 + 80 + 200
        assert len(shown['items']) == 4  # every denomination listed
        assert len(db.get_cash_collections()) == 1
        assert set(_counts(db).values()) == {0}

    def test_cancel_writes_nothing(self, controller, db):
        controller.view.confirm_collect_cash = lambda items, total: False
        controller.view.collect_cash_clicked.emit()

        assert _tables(db) == (0, 0)
        assert _counts(db)[(1.0, 'coin')] == 80

    def test_button_emits_signal(self, qapp):
        view = AdminScreenView(sim_mode=False)
        fired = []
        view.collect_cash_clicked.connect(lambda: fired.append(True))
        next(b for b in view.findChildren(QPushButton) if b.text() == "Collect cash").click()
        assert fired == [True]


class TestDashboard:
    @pytest.fixture
    def client(self, db):
        app.dependency_overrides[get_db] = lambda: db
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_db, None)

    def _login(self, client, db, role):
        create_account(db, role, "s3cret!", role)
        assert client.post("/login", json={"username": role, "password": "s3cret!"}).status_code == 200

    def test_requires_login(self, client):
        assert client.get("/accounting/collections").status_code == 401

    @pytest.mark.parametrize("role", ["admin", "operator"])
    def test_both_roles_read_collections_newest_first(self, client, db, role):
        db.record_cash_collection()
        db.update_cash_inventory(20, 3, 'bill')
        db.record_cash_collection()
        self._login(client, db, role)

        data = client.get("/accounting/collections").json()

        assert [c['total'] for c in data['collections']] == [60, 8 * 0 + 80 + 150 + 80 + 200]
        assert {i['denomination'] for i in data['collections'][0]['items']} == {1.0, 5.0, 20.0, 100.0}
        page = client.get("/accounting")
        assert page.status_code == 200
        assert "Collected" in page.text

    def test_revenue_since_last_collection_counts_completed_only(self, client, db):
        seed_transaction(db.conn, "usb", 10, status="completed", timestamp="2000-01-01 00:00:00")
        db.conn.commit()
        db.record_cash_collection()
        seed_transaction(db.conn, "wifi", 25)
        seed_transaction(db.conn, "usb", 99, status="print_failed")
        db.conn.commit()
        self._login(client, db, "operator")

        assert client.get("/accounting/collections").json()['revenue_since_last'] == 25

    def test_all_time_revenue_before_any_collection(self, client, db):
        seed_transaction(db.conn, "usb", 10)
        db.conn.commit()
        self._login(client, db, "operator")

        data = client.get("/accounting/collections").json()

        assert data['collections'] == [] and data['revenue_since_last'] == 10

    def test_no_write_route_for_collections(self, client, db):
        self._login(client, db, "admin")
        assert client.post("/accounting/collections").status_code == 405
