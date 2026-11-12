"""managers/accounting_report.py: the figures shared by the Admin Dashboard's
/accounting and the touchscreen's Reports screen (issue #130)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "SSP"))

from admin_dashboard.seed_demo_data import seed_transaction  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers import accounting_report as report  # noqa: E402

NOW = datetime(2025, 6, 18, 15, 30, 0)  # a Wednesday afternoon


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "report.db")
    init_db(path)
    database = DatabaseManager(db_path=path)
    yield database
    database.close()


class TestRangeStart:
    def test_today_is_local_midnight(self):
        assert report.range_start("today", NOW) == datetime(2025, 6, 18)

    def test_week_and_month_are_rolling(self):
        assert report.range_start("week", NOW) == NOW - timedelta(days=7)
        assert report.range_start("month", NOW) == NOW - timedelta(days=30)

    def test_all_has_no_lower_bound(self):
        assert report.range_start("all", NOW) is None

    def test_defaults_to_now(self):
        assert report.range_start("today") == datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def test_every_range_key_is_handled(self):
        for key in report.RANGE_KEYS:
            report.range_start(key, NOW)


class TestFigures:
    def _add(self, db, source, cost, when, status="completed"):
        seed_transaction(db.conn, source, cost, status=status, timestamp=when)
        db.conn.commit()

    def test_voucher_figures_carry_liability_whatever_the_window(self, db):
        figures = report.voucher_figures(db, datetime.now())
        assert set(figures) >= {"change_dispensed", "voucher_issued", "voucher_applied", "liability"}

    def test_collection_figures_with_no_collection(self, db):
        self._add(db, "usb", 10, datetime.now())
        figures = report.collection_figures(db)
        assert figures["collections"] == []
        assert figures["last_collected_at"] is None
        assert figures["revenue_since_last"] == 10

    def test_revenue_since_last_counts_only_after_the_collection(self, db):
        self._add(db, "usb", 10, datetime.now() - timedelta(hours=2))
        db.record_cash_collection(collected_at=datetime.now() - timedelta(hours=1))
        self._add(db, "wifi", 7, datetime.now())
        figures = report.collection_figures(db)
        assert len(figures["collections"]) == 1
        assert figures["revenue_since_last"] == 7

    def test_accounting_data_shape_and_window(self, db):
        self._add(db, "usb", 10, datetime.now())
        self._add(db, "email", 5, datetime.now() - timedelta(days=3))
        today = report.accounting_data(db, "today")
        assert today["range"] == "today"
        assert [r["source"] for r in today["sources"]] == ["usb", "wifi", "email", "scanner"]
        assert sum(r["revenue"] for r in today["sources"]) == 10
        assert sum(r["revenue"] for r in report.accounting_data(db, "week")["sources"]) == 15
        assert set(today) == {"range", "sources", "vouchers"}
