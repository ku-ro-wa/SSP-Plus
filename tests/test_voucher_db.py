"""
Voucher persistence against a real temp SQLite file: init_db() creates the
tables, columns and settings, and VoucherManager issues/looks up/Applies
through the real DatabaseManager (VoucherDBMixin), not FakeVoucherDB.
"""
import sqlite3
from datetime import datetime, timedelta

import pytest

import managers.voucher_manager as vm
from database.db_manager import DatabaseManager
from database.models import init_db
from managers.voucher_manager import VoucherManager


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture(autouse=True)
def fast_qr(monkeypatch):
    monkeypatch.setattr(vm, '_generate_qr_bytes', lambda payload: payload.encode())


@pytest.fixture
def db(db_path):
    manager = DatabaseManager(db_path=db_path)
    yield manager
    manager.close()


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _all_cells(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return [cell for row in conn.execute(f"SELECT * FROM {table}") for cell in row]
    finally:
        conn.close()


class TestInitDb:
    def test_creates_voucher_tables(self, db_path):
        assert {'voucher_id', 'code_hash', 'initial_value', 'remaining_value',
                'created_at', 'expires_at', 'payment_ref'} <= _columns(db_path, 'vouchers')
        assert {'voucher_id', 'amount', 'payment_ref', 'applied_at'} <= _columns(
            db_path, 'voucher_applications')

    def test_seeds_voucher_settings_with_defaults(self, db):
        assert db.get_setting('voucher_expiry_days') == 30
        assert db.get_setting('low_change_warning_threshold') == 20

    def test_rerun_keeps_operator_changed_settings(self, db_path, db):
        db.update_setting('voucher_expiry_days', 45)
        db.update_setting('low_change_warning_threshold', 50)
        init_db(db_path)
        assert db.get_setting('voucher_expiry_days') == 45
        assert db.get_setting('low_change_warning_threshold') == 50

    def test_rerun_keeps_existing_vouchers(self, db_path, db, clock):
        issued = VoucherManager(db, now_fn=clock).issue(7)
        init_db(db_path)
        assert VoucherManager(db, now_fn=clock).balance(issued.code).remaining == 7

    def test_upgrades_a_db_from_before_vouchers(self, tmp_path):
        path = str(tmp_path / "old.db")
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, file_name TEXT,
            pages INTEGER, copies INTEGER, color_mode TEXT, total_cost REAL,
            amount_paid REAL, change_given REAL, status TEXT)""")
        conn.execute("INSERT INTO transactions (file_name, total_cost, amount_paid, change_given, status) "
                     "VALUES ('old.pdf', 5, 10, 5, 'completed')")
        conn.commit()
        conn.close()

        init_db(path)

        assert {'change_dispensed', 'voucher_issued', 'voucher_applied', 'payment_ref'} <= _columns(
            path, 'transactions')
        assert 'vouchers' in {r[0] for r in sqlite3.connect(path).execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        old = DatabaseManager(db_path=path).get_transaction_history()[0]
        assert (old['file_name'], old['voucher_issued'], old['voucher_applied']) == ('old.pdf', 0, 0)


class TestRealDbVouchers:
    def test_issue_then_apply_survives_a_restart(self, db_path, clock):
        first = DatabaseManager(db_path=db_path)
        issued = VoucherManager(first, now_fn=clock).issue(12, payment_ref="pay-1")
        first.close()

        second = DatabaseManager(db_path=db_path)
        result = VoucherManager(second, now_fn=clock).apply([issued.display_code], 5, payment_ref="pay-2")
        second.close()

        assert result.success and result.total_applied == 5
        third = DatabaseManager(db_path=db_path)
        balance = VoucherManager(third, now_fn=clock).balance(issued.code.lower())
        assert balance.remaining == 7
        assert balance.expires_at == issued.expires_at
        third.close()

    def test_expiry_comes_from_the_settings_table(self, db, clock):
        db.update_setting('voucher_expiry_days', 10)
        issued = VoucherManager(db, now_fn=clock).issue(5)
        assert issued.expires_at == clock.now + timedelta(days=10)

    def test_only_a_hash_of_the_code_is_stored(self, db_path, db, clock):
        manager = VoucherManager(db, now_fn=clock)
        issued = manager.issue(9, payment_ref="pay-1")
        manager.apply([issued.code], 4, payment_ref="pay-2")

        for table in ('vouchers', 'voucher_applications', 'transactions', 'settings', 'error_log'):
            for cell in _all_cells(db_path, table):
                text = str(cell).upper()
                assert issued.code not in text
                assert issued.display_code not in text

    def test_no_log_line_contains_the_code(self, db, clock, capsys):
        manager = VoucherManager(db, now_fn=clock)
        issued = manager.issue(9)
        manager.balance(issued.display_code)
        manager.apply([issued.code], 4)
        out = capsys.readouterr().out.upper()
        assert issued.code not in out
        assert issued.display_code not in out

    def test_several_vouchers_drain_in_order_with_one_link_row_each(self, db_path, db, clock):
        manager = VoucherManager(db, now_fn=clock)
        a, b, c = manager.issue(4), manager.issue(6), manager.issue(10)

        result = manager.apply([a.code, b.code, c.code], 13, payment_ref="pay-9")

        assert [x['amount'] for x in result.applications] == [4, 6, 3]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT voucher_id, amount, payment_ref FROM voucher_applications ORDER BY id").fetchall()
        conn.close()
        assert rows == [(a.voucher_id, 4, "pay-9"), (b.voucher_id, 6, "pay-9"), (c.voucher_id, 3, "pay-9")]
        assert manager.balance(c.code).remaining == 7

    def test_fully_used_voucher_is_rejected(self, db, clock):
        manager = VoucherManager(db, now_fn=clock)
        issued = manager.issue(5)
        manager.apply([issued.code], 5)
        assert manager.balance(issued.code).status == vm.LookupStatus.USED
        assert manager.balance(issued.code).message == vm.MSG_FULLY_USED
        assert not manager.apply([issued.code], 1).success

    def test_expired_voucher_is_rejected(self, db, clock):
        manager = VoucherManager(db, now_fn=clock)
        issued = manager.issue(5)
        clock.advance(days=30, seconds=1)
        assert manager.balance(issued.code).status == vm.LookupStatus.EXPIRED
        result = manager.balance(issued.code)
        assert result.message == "This voucher expired on October 31, 2026"
        assert not manager.apply([issued.code], 1).success
        assert int(db.get_setting('voucher_failed_attempts', 0)) == 0  # a real code isn't a guess

    def test_lockout_is_kiosk_wide_across_restarts(self, db_path, clock):
        first = DatabaseManager(db_path=db_path)
        issued = VoucherManager(first, now_fn=clock).issue(5)
        for _ in range(4):
            VoucherManager(first, now_fn=clock).balance("ZZZZ-ZZZZ")
        first.close()

        second = DatabaseManager(db_path=db_path)
        manager = VoucherManager(second, now_fn=clock)
        assert manager.apply(["ZZZZ-ZZZZ"], 5).locked
        assert manager.balance(issued.code).locked
        clock.advance(minutes=6)
        assert manager.balance(issued.code).remaining == 5
        second.close()
