"""
Multi-file transactions, data layer only (#119 / #122): PrintItem helpers,
the transaction_files migration, refund_partly_printed, the accounting
queries, and the Admin Dashboard against a database from before the change.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

import admin_dashboard.dependencies as dashboard_deps
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from admin_dashboard.main import app
from database.db_manager import DatabaseManager
from database.models import init_db, migrate_transaction_files
from managers.print_items import MAX_FILES_PER_TRANSACTION, PrintItem, summary_columns, total_sheets
from managers.print_refund import PARTLY_PRINTED, refund_failed_print, refund_partly_printed
from screens.voucher.model import PESO, VoucherModel


def item(name="a.pdf", pages=(1, 2), copies=1, color="Black and White", cost=2.0):
    return PrintItem(pdf_data={'path': f"/tmp/{name}", 'filename': name}, pages=list(pages),
                     copies=copies, color_mode=color, cost=cost)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.db")
    init_db(path)
    d = DatabaseManager(db_path=path)
    yield d
    d.close()


def log(db, items, ref="ref1", status="paid", total=None, source="usb", **extra):
    data = {**summary_columns(items), 'total_cost': total if total is not None else sum(i.cost for i in items),
            'amount_paid': 100.0, 'change_given': 0.0, 'status': status, 'source': source,
            'payment_ref': ref, 'items': items}
    data.update(extra)
    assert db.log_transaction(data)


class TestPrintItems:
    def test_limit(self):
        assert MAX_FILES_PER_TRANSACTION == 10

    def test_item_properties(self):
        i = item(pages=(1, 3, 4), copies=2)
        assert (i.path, i.file_name, i.sheets) == ("/tmp/a.pdf", "a.pdf", 6)

    def test_file_name_falls_back_to_the_path_basename(self):
        assert PrintItem(pdf_data={'path': '/x/y/z.pdf'}, pages=[1]).file_name == "z.pdf"

    def test_one_item_matches_the_old_row(self):
        assert summary_columns([item(pages=(1, 2, 3), copies=2, color="Color")]) == {
            'file_name': 'a.pdf', 'pages': 3, 'copies': 2, 'color_mode': 'Color', 'file_count': 1}

    def test_several_items(self):
        items = [item("a.pdf", (1, 2), 2), item("b.pdf", (1,), 3), item("c.pdf", (1, 2, 3), 1)]
        cols = summary_columns(items)
        assert total_sheets(items) == 10
        assert cols == {'file_name': 'a.pdf +2 more', 'pages': 10, 'copies': 1,
                        'color_mode': 'Black and White', 'file_count': 3}

    def test_mixed_color_modes(self):
        cols = summary_columns([item(), item("b.pdf", color="Color")])
        assert cols['color_mode'] == "Mixed"


class TestMigration:
    def _old_db(self, tmp_path):
        path = str(tmp_path / "old.db")
        init_db(path)
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE transaction_files")
        conn.execute("ALTER TABLE transactions DROP COLUMN file_count")
        conn.execute("INSERT INTO transactions (timestamp, file_name, pages, copies, color_mode, total_cost, "
                     "amount_paid, change_given, status, source) "
                     "VALUES ('2026-01-01', 'old.pdf', 1, 1, 'Color', 5, 5, 0, 'completed', 'usb')")
        conn.commit()
        return path, conn

    def test_old_database_migrates(self, tmp_path):
        path, conn = self._old_db(tmp_path)
        migrate_transaction_files(conn)
        assert conn.execute("SELECT file_count FROM transactions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM transaction_files").fetchone()[0] == 0
        conn.close()

    def test_init_db_twice_is_harmless(self, tmp_path):
        path, conn = self._old_db(tmp_path)
        conn.close()
        init_db(path)
        init_db(path)
        c = sqlite3.connect(path)
        assert c.execute("SELECT file_count FROM transactions").fetchone()[0] == 1
        c.close()

    def test_database_without_tables_is_left_alone(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "empty.db"))
        migrate_transaction_files(conn)
        conn.close()


class TestLogTransactionFiles:
    def test_writes_one_row_per_item(self, db):
        log(db, [item("a.pdf", cost=2), item("b.pdf", (1,), 2, "Color", 6)])
        rows = db.get_transaction_files("ref1")
        assert [(r['position'], r['file_name'], r['pages'], r['copies'], r['color_mode'], r['cost'], r['status'])
                for r in rows] == [(1, 'a.pdf', 2, 1, 'Black and White', 2, 'pending'),
                                   (2, 'b.pdf', 1, 2, 'Color', 6, 'pending')]
        assert db.get_transaction_by_ref("ref1")['file_count'] == 2

    def test_abandoned_payment_files_are_not_printed(self, db):
        log(db, [item(), item("b.pdf")], status="cancelled_partial_payment")
        assert {r['status'] for r in db.get_transaction_files("ref1")} == {'not_printed'}

    def test_no_items_writes_no_file_rows_and_count_defaults_to_one(self, db):
        db.log_transaction({'file_name': 'x.pdf', 'pages': 1, 'copies': 1, 'color_mode': 'Color',
                            'total_cost': 1, 'amount_paid': 1, 'change_given': 0, 'status': 'paid',
                            'payment_ref': 'r'})
        assert db.get_transaction_files('r') == []
        assert db.get_transaction_by_ref('r')['file_count'] == 1

    def test_duplicate_ref_writes_nothing(self, db):
        log(db, [item()])
        assert db.log_transaction({**summary_columns([item()]), 'total_cost': 1, 'amount_paid': 1,
                                   'change_given': 0, 'status': 'paid', 'payment_ref': 'ref1',
                                   'items': [item()]}) is False
        assert len(db.get_transaction_files("ref1")) == 1

    def test_set_status(self, db):
        log(db, [item(), item("b.pdf")])
        assert db.set_transaction_file_status("ref1", 2, "printed")
        assert [r['status'] for r in db.get_transaction_files("ref1")] == ['pending', 'printed']
        assert not db.set_transaction_file_status("ref1", 9, "printed")


class TestRefundPartlyPrinted:
    def _three(self, db, costs=(2.4, 3.4, 4.4)):
        log(db, [item("a.pdf", cost=costs[0]), item("b.pdf", cost=costs[1]), item("c.pdf", cost=costs[2])])

    def test_refunds_failed_and_unsent_in_one_voucher_rounded_once(self, db):
        self._three(db)
        db.set_transaction_file_status("ref1", 3, "printed")   # last file goes first
        out = refund_partly_printed(db, "ref1", failed_position=2, error_message="paper out")

        assert out.applied and out.amount == 6   # round(3.4 + 2.4) = 6; per-file rounding would give 5
        assert out.voucher.value == 6
        assert [r['status'] for r in db.get_transaction_files("ref1")] == ['not_printed', 'failed', 'printed']
        row = db.get_transaction_by_ref("ref1")
        assert row['status'] == PARTLY_PRINTED
        assert row['voucher_issued'] == 6
        assert row['error_message'] == "paper out"

    def test_second_call_does_nothing(self, db):
        self._three(db)
        db.set_transaction_file_status("ref1", 3, "printed")
        refund_partly_printed(db, "ref1", 2)
        again = refund_partly_printed(db, "ref1", 2)
        assert not again.applied and again.voucher is None
        assert db.get_transaction_by_ref("ref1")['voucher_issued'] == 6

    def test_vouchers_off_reports_failure(self, db, monkeypatch):
        self._three(db)
        monkeypatch.setattr("managers.print_refund.send_operator_alert", lambda *a, **k: None)
        db.update_setting('vouchers_enabled', 0)
        db.set_transaction_file_status("ref1", 3, "printed")
        out = refund_partly_printed(db, "ref1", 2)
        assert out.voucher_failed and out.voucher is None and out.amount == 6
        assert db.get_transaction_by_ref("ref1")['status'] == PARTLY_PRINTED

    def test_unknown_ref(self, db):
        assert not refund_partly_printed(db, "nope", 1).applied

    def test_nothing_printed_failure_still_refunds_in_full(self, db):
        self._three(db)
        out = refund_failed_print(db, "ref1", "boom")
        assert out.applied and out.amount == int(round(2.4 + 3.4 + 4.4))
        assert db.get_transaction_by_ref("ref1")['status'] == 'print_failed'


class TestAccounting:
    def _row(self, db, status, source="usb"):
        return {r['source']: r for r in db.get_accounting_summary()}[source]

    def test_partly_printed_adds_only_printed_files(self, db):
        log(db, [item("a.pdf", cost=2), item("b.pdf", cost=3), item("c.pdf", cost=4)], total=9)
        db.set_transaction_file_status("ref1", 3, "printed")
        refund_partly_printed(db, "ref1", 2)
        log(db, [item(cost=5)], ref="ref2", status="completed")

        usb = self._row(db, "usb")
        assert usb['revenue'] == 4 + 5
        assert usb['transaction_count'] == 2

    def test_paid_and_failed_rows_still_excluded(self, db):
        log(db, [item(cost=5)], ref="r1", status="paid")
        log(db, [item(cost=5)], ref="r2", status="print_failed")
        assert self._row(db, "usb") == {'source': 'usb', 'revenue': 0, 'transaction_count': 0}

    def test_partly_printed_in_change_and_voucher_totals(self, db):
        log(db, [item(cost=2), item("b.pdf", cost=3)], total=5, change_dispensed=7, voucher_applied=1)
        db.set_transaction_file_status("ref1", 2, "printed")
        refund_partly_printed(db, "ref1", 1)

        totals = db.get_change_and_voucher_totals()
        assert totals == {'change_dispensed': 7, 'voucher_issued': 2, 'voucher_applied': 1}


class TestVoucherScreenCopy:
    def test_partial_refund_copy(self):
        m = VoucherModel()
        m.reason = VoucherModel.PARTIAL_REFUND
        m.state = VoucherModel.ISSUED
        m.value = 6
        m.set_file_counts(1, 3)
        assert m.title() == "Some of your files didn't print"
        assert m.body() == f"1 of 3 files printed. We've issued a refund voucher worth {PESO}6 for the rest."

    def test_partial_refund_failure_copy(self):
        m = VoucherModel()
        m.set_failure(6, VoucherModel.PARTIAL_REFUND)
        m.set_file_counts(1, 3)
        assert "1 of 3 files printed" in m.body()
        assert f"{PESO}6" in m.body() and "attendant" in m.body()


class TestDashboardOnOldDatabase:
    def test_accounting_shows_real_figures(self, tmp_path, monkeypatch):
        path = str(tmp_path / "old.db")
        init_db(path)
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE transaction_files")
        conn.execute("ALTER TABLE transactions DROP COLUMN file_count")
        conn.execute("INSERT INTO transactions (timestamp, file_name, pages, copies, color_mode, total_cost, "
                     "amount_paid, change_given, status, source) "
                     "VALUES (datetime('now'), 'old.pdf', 1, 1, 'Color', 12, 12, 0, 'completed', 'usb')")
        conn.commit()
        conn.close()

        class Cfg:
            sim_mode = False
        monkeypatch.setattr(dashboard_deps, "get_config", lambda: Cfg())
        monkeypatch.setattr(dashboard_deps, "DatabaseManager", lambda: DatabaseManager(db_path=path))
        seed = DatabaseManager(db_path=path)
        create_account(seed, "admin1", "s3cret!", "admin")
        seed.close()

        app.dependency_overrides.pop(get_db, None)
        client = TestClient(app)
        client.post("/login", json={"username": "admin1", "password": "s3cret!"})
        data = client.get("/accounting/data?range=all").json()

        usb = next(r for r in data["sources"] if r["source"] == "usb") if "sources" in data else None
        assert usb is not None and usb["revenue"] == 12 and usb["transaction_count"] == 1
