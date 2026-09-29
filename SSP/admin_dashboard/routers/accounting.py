# admin_dashboard/routers/accounting.py
#
# /accounting renders the login-gated summary table + Chart.js bar chart;
# /accounting/data is the JSON aggregate endpoint the page's time-filter
# buttons re-fetch from (issue #15, chart added in issue #16). Both are
# reachable by either dashboard role (`dev` or `admin`) — read access isn't
# role-gated. /paper-reset (issue #17) is the one write action here, and it
# is role-gated to `dev` via require_dev.

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from admin_dashboard.auth import get_current_user, get_current_user_page, require_dev
from admin_dashboard.dependencies import get_db

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

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


@router.get("/accounting/data")
def accounting_data(
    time_range: RangeKey = Query("today", alias="range"),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    sources = db.get_accounting_summary(since=_range_start(time_range))
    return {"range": time_range, "sources": sources}


@router.get("/accounting", response_class=HTMLResponse)
def accounting_page(
    request: Request,
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    sources = db.get_accounting_summary(since=_range_start("today"))
    return templates.TemplateResponse(
        request,
        "accounting.html",
        {
            "request": request,
            "range": "today",
            "sources": sources,
            # Jinja2Templates doesn't register Flask's `tojson` filter, so
            # the chart's initial render (issue #16) gets its data as a
            # pre-serialized string instead.
            "sources_json": json.dumps(sources),
        },
    )


@router.post("/paper-reset")
def paper_reset(
    current_user: dict = Depends(require_dev),
    db=Depends(get_db),
):
    """Resets the kiosk's paper count — the fallback for the SMS
    fuzzy-match reset flow from Phase 8 (issue #17). `dev`-only: require_dev
    returns 401 unauthenticated, 403 for the read-only `admin` role."""
    db.update_paper_count(PAPER_FULL_COUNT)
    return {"paper_count": PAPER_FULL_COUNT}
