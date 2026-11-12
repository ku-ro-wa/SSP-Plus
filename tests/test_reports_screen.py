"""Kiosk Admin's Reports screen (issue #130): its model reads the same figures as the
Admin Dashboard's /accounting, for every range, from one seeded database."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "SSP"))

from admin_dashboard.cli import create_account  # noqa: E402
from admin_dashboard.dependencies import get_db  # noqa: E402
from admin_dashboard.main import app  # noqa: E402
from admin_dashboard.seed_demo_data import seed_transaction  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.accounting_report import RANGE_KEYS  # noqa: E402
from screens.reports.model import RANGES, ReportsModel  # noqa: E402


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "reports.db")
    init_db(path)
    database = DatabaseManager(db_path=path)
    now = datetime.now()
    # Spread across every window's edge: today, 3 days, 20 days, 100 days ago.
    for source, cost, age in (("usb", 40, timedelta(minutes=5)), ("wifi", 25, timedelta(days=3)),
                              ("email", 10, timedelta(days=20)), ("scanner", 15, timedelta(days=100)),
                              ("usb", 5, timedelta(days=3)), ("usb", 99, timedelta(minutes=1))):
        status = "print_failed" if cost == 99 else "completed"
        seed_transaction(database.conn, source, cost, status=status, timestamp=now - age)
    database.conn.commit()
    database.record_cash_collection(collected_at=now - timedelta(days=2))
    seed_transaction(database.conn, "wifi", 7, timestamp=now - timedelta(days=1))
    database.conn.commit()
    yield database
    database.close()


@pytest.fixture
def dashboard(db):
    create_account(db, "boss", "pw-for-tests", "operator")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    login = client.post("/login", json={"username": "boss", "password": "pw-for-tests"}, follow_redirects=False)
    assert login.status_code in (200, 303), login.text
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_the_screen_offers_the_dashboards_ranges():
    assert [key for _, key in RANGES] == list(RANGE_KEYS)


@pytest.mark.parametrize("range_key", RANGE_KEYS)
def test_model_matches_accounting_data(db, dashboard, range_key):
    response = dashboard.get(f"/accounting/data?range={range_key}")
    assert response.status_code == 200, response.text
    expected = response.json()
    report = ReportsModel(db).report(range_key)
    assert report["range"] == expected["range"]
    assert report["sources"] == expected["sources"]
    assert report["vouchers"] == expected["vouchers"]


def test_model_collections_match_the_dashboards(db, dashboard):
    response = dashboard.get("/accounting/collections")
    assert response.status_code == 200, response.text
    expected = response.json()
    cash = ReportsModel(db).report("today")["cash"]
    assert cash["revenue_since_last"] == expected["revenue_since_last"] == 47  # 40 usb + 7 wifi; the 99 print_failed is not revenue
    assert [c["id"] for c in cash["collections"]] == [c["id"] for c in expected["collections"]]
    assert str(cash["last_collected_at"]) == str(expected["last_collected_at"])


def test_model_remembers_the_range():
    model = ReportsModel(db_manager=None)
    assert model.range_key == "today"


def test_screen_renders_a_report_and_has_no_timeout(db):
    from unittest.mock import MagicMock

    from PyQt5.QtWidgets import QApplication

    from screens.reports import ReportsController

    QApplication.instance() or QApplication([])
    main_app = MagicMock()
    main_app.admin_screen.db_manager = db
    screen = ReportsController(main_app)
    assert not hasattr(screen, "timeout_policy")
    screen.on_enter()
    assert screen.view.range_buttons["today"].isChecked()
    assert screen.view.voucher_values["liability"].text() == "₱0.00"
    screen.view.range_buttons["all"].click()
    assert screen.view.range_buttons["all"].isChecked()
    screen.view.back_button.click()
    main_app.show_screen.assert_called_with("admin")
