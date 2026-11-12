"""
The touchscreen data viewer shows what the Dashboard's /logs shows (issue #131):
the same columns, the same rows from the same DatabaseManager reads, the same
page size, newest first. Real controller, view and model on a temp DB, offscreen.
"""
import os
import re

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from SSP.admin_dashboard.main import app as dashboard  # noqa: E402
from admin_dashboard.cli import create_account  # noqa: E402
from admin_dashboard.dependencies import get_db  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.log_pages import PAGE_SIZE  # noqa: E402
from screens.data_viewer.controller import DataViewerController  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / 'viewer.db')
    init_db(path)
    d = DatabaseManager(db_path=path)
    yield d
    d.close()


@pytest.fixture
def viewer(qapp, db):
    controller = DataViewerController(MagicMock(), db)
    controller.on_enter()
    return controller


@pytest.fixture
def client(db):
    dashboard.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(dashboard)
        create_account(db, "u", "s3cret!", "operator")
        c.post("/login", json={"username": "u", "password": "s3cret!"})
        yield c
    finally:
        dashboard.dependency_overrides.pop(get_db, None)


def add_transactions(db, n, source='usb'):
    for i in range(n):
        db.conn.execute(
            "INSERT INTO transactions (timestamp, file_name, pages, copies, color_mode, total_cost,"
            " amount_paid, change_given, status, source) VALUES (?, ?, 2, 1, 'BW', 5, 10, 5, 'completed', ?)",
            (f"2026-10-01 10:{i // 60:02d}:{i % 60:02d}", f"file{i}.pdf", source))
    db.conn.commit()


def add_errors(db, n):
    for i in range(n):
        db.conn.execute(
            "INSERT INTO error_log (timestamp, error_type, error_message, screen_name, resolved)"
            " VALUES (?, 'Printing Error', ?, 'printer', ?)",
            (f"2026-10-01 10:{i // 60:02d}:{i % 60:02d}", f"jam {i}", i % 2))
    db.conn.commit()


def headers(table):
    return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]


def cells(table, row):
    return [table.item(row, c).text() for c in range(table.columnCount())]


def logs_headers(html, section):
    block = re.search(rf'<section id="{section}">.*?</thead>', html, re.S).group(0)
    return re.findall(r'<th(?:\s[^>]*)?>([^<]*)</th>', block)


def test_transaction_headers_match_logs_after_the_id(viewer, client, db):
    add_transactions(db, 1)
    viewer.model.refresh_all_data()
    assert headers(viewer.view.transactions_table) == ["ID", *logs_headers(client.get("/logs").text, "transactions")]
    assert logs_headers(client.get("/logs").text, "transactions") == [
        "Time", "File", "Source", "Pages", "Copies", "Colour", "Cost", "Paid", "Change", "Status"]


def test_error_headers_match_logs(viewer, client, db):
    add_errors(db, 1)
    viewer.model.refresh_all_data()
    assert headers(viewer.view.error_log_table) == logs_headers(client.get("/logs").text, "error-log")
    assert headers(viewer.view.error_log_table)[-1] == "Resolved"


def test_transaction_row_shows_source_and_change(viewer, db):
    add_transactions(db, 1, source='wifi')
    viewer.model.refresh_all_data()
    row = cells(viewer.view.transactions_table, 0)
    assert row[3] == 'wifi' and row[-2] == '₱5.00' and row[-3] == '₱10.00' and row[-1] == 'completed'


def test_error_row_shows_resolved(viewer, db):
    add_errors(db, 2)
    viewer.model.refresh_all_data()
    resolved = [cells(viewer.view.error_log_table, r)[-1] for r in range(2)]
    assert sorted(resolved) == ['no', 'yes']


def test_rows_pages_and_order_match_logs(viewer, client, db):
    add_transactions(db, PAGE_SIZE + 5)
    add_errors(db, PAGE_SIZE + 5)
    viewer.model.refresh_all_data()
    table = viewer.view.transactions_table

    assert table.rowCount() == PAGE_SIZE
    dash = client.get("/logs/data").json()
    assert [cells(table, r)[2] for r in range(table.rowCount())] == [t["file_name"] for t in dash["transactions"]["rows"]]
    assert viewer.view.transactions_page_label.text() == f"Page 1 of {dash['transactions']['pages']}" == "Page 1 of 2"

    viewer.model.next_transactions_page()
    dash2 = client.get("/logs/data?tx_page=2").json()["transactions"]
    assert [cells(table, r)[2] for r in range(table.rowCount())] == [t["file_name"] for t in dash2["rows"]]
    assert table.rowCount() == 5 and viewer.view.transactions_page_label.text() == "Page 2 of 2"

    viewer.model.next_errors_page()
    errs = viewer.view.error_log_table
    dash_err = client.get("/logs/data?err_page=2").json()["errors"]
    assert [cells(errs, r)[2] for r in range(errs.rowCount())] == [e["error_message"] for e in dash_err["rows"]]


def test_newer_older_buttons_follow_the_page(viewer, db):
    add_transactions(db, PAGE_SIZE + 1)
    viewer.model.refresh_all_data()
    view = viewer.view
    assert not view.newer_transactions_button.isEnabled() and view.older_transactions_button.isEnabled()
    view.older_transactions_button.click()
    assert view.newer_transactions_button.isEnabled() and not view.older_transactions_button.isEnabled()
    view.older_transactions_button.click()  # past the end stays on the last page
    assert viewer.model.transactions_page == 2
    view.newer_transactions_button.click()
    assert viewer.model.transactions_page == 1


def test_empty_logs_render(viewer):
    assert viewer.view.transactions_table.rowCount() == 0
    assert viewer.view.transactions_page_label.text() == "Page 1 of 1"
    assert viewer.view.error_log_table.rowCount() == 0
