# admin_dashboard/routers/accounting.py
#
# /accounting renders the login-gated summary table + Chart.js bar chart;
# /accounting/data is the JSON aggregate endpoint the page's time-filter
# buttons re-fetch from (issue #15, chart added in issue #16). Both are
# reachable by either dashboard role (`admin` or `operator`) — read access isn't
# role-gated. Both also carry the change dispensed, Voucher value issued /
# Applied, and outstanding Voucher liability (issue #28). /paper-reset
# (issue #17) is the one write action here, and it is role-gated to `admin`
# via require_write_role.

import json
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from admin_dashboard.auth import get_current_user, get_current_user_page, require_write_role
from admin_dashboard.dependencies import get_db
from admin_dashboard.templating import templates
from managers.admin_actions import ACTION_PAPER_RESET, WHERE_DASHBOARD, record_action

router = APIRouter()


RangeKey = Literal["today", "week", "month", "all"]

# The paper count a reset restores, mirroring the Kiosk Admin touchscreen's
# own "Refill" action (screens/admin/model.py's AdminModel.reset_paper_count)
# — a separate system with the same convention, not a shared code path (see
# CONTEXT.md's Kiosk Admin term for why the two stay independent).
PAPER_FULL_COUNT = 100


def _range_start(range_key: RangeKey):
    """Start of the window for `range_key`, or None for "all" (no lower
    bound). "today" is since local midnight; "week"/"month" are rolling
    windows (now minus 7/30 days) rather than calendar week/month, so the
    boundary doesn't depend on which weekday/date it currently is."""
    now = datetime.now()
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "week":
        return now - timedelta(days=7)
    if range_key == "month":
        return now - timedelta(days=30)
    return None


def _voucher_figures(db, since):
    """Change / Voucher amounts for the window plus the outstanding Voucher
    liability, which is as of now whatever the window (issue #28)."""
    return {
        **db.get_change_and_voucher_totals(since=since),
        "liability": db.get_voucher_liability(datetime.now()),
    }


def _collection_figures(db):
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


@router.get("/accounting/collections")
def accounting_collections(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Read-only for either role; recording a collection happens only on the kiosk."""
    return _collection_figures(db)


@router.get("/accounting/data")
def accounting_data(
    time_range: RangeKey = Query("today", alias="range"),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    since = _range_start(time_range)
    return {
        "range": time_range,
        "sources": db.get_accounting_summary(since=since),
        "vouchers": _voucher_figures(db, since),
    }


@router.get("/accounting", response_class=HTMLResponse)
def accounting_page(
    request: Request,
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    since = _range_start("today")
    sources = db.get_accounting_summary(since=since)
    return templates.TemplateResponse(
        request,
        "accounting.html",
        {
            "request": request,
            "active": "accounting",
            "range": "today",
            "sources": sources,
            # Jinja2Templates doesn't register Flask's `tojson` filter, so
            # the chart's initial render (issue #16) gets its data as a
            # pre-serialized string instead.
            "sources_json": json.dumps(sources),
            "vouchers": _voucher_figures(db, since),
            "cash": _collection_figures(db),
        },
    )


@router.post("/paper-reset")
def paper_reset(
    request: Request,
    current_user: dict = Depends(require_write_role),
    db=Depends(get_db),
):
    """Resets the kiosk's paper count — the fallback for the SMS
    fuzzy-match reset flow from Phase 8 (issue #17). `admin`-only: require_write_role
    returns 401 unauthenticated, 403 for the read-only `operator` role."""
    old = db.get_setting('paper_count', default=None)
    db.update_paper_count(PAPER_FULL_COUNT)
    record_action(
        db, ACTION_PAPER_RESET, old, PAPER_FULL_COUNT, actor=current_user["username"],
        where=WHERE_DASHBOARD, ip=request.client.host if request.client else None,
    )
    return {"paper_count": PAPER_FULL_COUNT}
