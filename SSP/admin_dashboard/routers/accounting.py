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

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from admin_dashboard.auth import get_current_user, get_current_user_page, require_write_role
from admin_dashboard.dependencies import get_db
from admin_dashboard.templating import templates
from managers.accounting_report import (
    RangeKey,
    accounting_data as build_accounting_data,
    collection_figures,
    range_start,
    voucher_figures,
)

router = APIRouter()

# The paper count a reset restores, mirroring the Kiosk Admin touchscreen's
# own "Refill" action (screens/admin/model.py's AdminModel.reset_paper_count)
# — a separate system with the same convention, not a shared code path (see
# CONTEXT.md's Kiosk Admin term for why the two stay independent).
PAPER_FULL_COUNT = 100


@router.get("/accounting/collections")
def accounting_collections(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Read-only for either role; recording a collection happens only on the kiosk."""
    return collection_figures(db)


@router.get("/accounting/data")
def accounting_data(
    time_range: RangeKey = Query("today", alias="range"),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    return build_accounting_data(db, time_range)


@router.get("/accounting", response_class=HTMLResponse)
def accounting_page(
    request: Request,
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    since = range_start("today")
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
            "vouchers": voucher_figures(db, since),
            "cash": collection_figures(db),
        },
    )


@router.post("/paper-reset")
def paper_reset(
    current_user: dict = Depends(require_write_role),
    db=Depends(get_db),
):
    """Resets the kiosk's paper count — the fallback for the SMS
    fuzzy-match reset flow from Phase 8 (issue #17). `admin`-only: require_write_role
    returns 401 unauthenticated, 403 for the read-only `operator` role."""
    db.update_paper_count(PAPER_FULL_COUNT)
    return {"paper_count": PAPER_FULL_COUNT}
