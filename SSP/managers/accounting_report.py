# managers/accounting_report.py
#
# The figures behind the Admin Dashboard's /accounting page and the touchscreen's
# Reports screen (issue #130). One implementation, so the two can't disagree.

from datetime import datetime, timedelta
from typing import Literal

RangeKey = Literal["today", "week", "month", "all"]
RANGE_KEYS = ("today", "week", "month", "all")


def range_start(range_key, now=None):
    """Start of the window for `range_key`, or None for "all" (no lower
    bound). "today" is since local midnight; "week"/"month" are rolling
    windows (now minus 7/30 days) rather than calendar week/month, so the
    boundary doesn't depend on which weekday/date it currently is."""
    now = now or datetime.now()
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "week":
        return now - timedelta(days=7)
    if range_key == "month":
        return now - timedelta(days=30)
    return None


def voucher_figures(db, since):
    """Change / Voucher amounts for the window plus the outstanding Voucher
    liability, which is as of now whatever the window (issue #28)."""
    return {
        **db.get_change_and_voucher_totals(since=since),
        "liability": db.get_voucher_liability(datetime.now()),
    }


def collection_figures(db):
    """The Collected table's data (issue #110): collections newest first, and
    completed revenue since the last one (all time if there has been none).
    Collected coins are the operator's physical count, not takings."""
    last = db.get_last_collection_time()
    since_last = sum(r["revenue"] for r in db.get_accounting_summary(since=last))
    return {
        "collections": db.get_cash_collections(),
        "last_collected_at": last,
        "revenue_since_last": since_last,
    }


def accounting_data(db, range_key):
    """What /accounting/data returns for `range_key`."""
    since = range_start(range_key)
    return {
        "range": range_key,
        "sources": db.get_accounting_summary(since=since),
        "vouchers": voucher_figures(db, since),
    }
