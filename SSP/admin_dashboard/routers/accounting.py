# admin_dashboard/routers/accounting.py
#
# /accounting renders the login-gated summary table; /accounting/data is
# the JSON aggregate endpoint the page's time-filter buttons re-fetch from
# (issue #15). Both are reachable by either dashboard role (`dev` or
# `admin`) — read access isn't role-gated, only the paper-count reset
# write action (issue #17) will be.

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from admin_dashboard.auth import get_current_user
from admin_dashboard.dependencies import get_db

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

RangeKey = Literal["today", "week", "month", "all"]


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
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    sources = db.get_accounting_summary(since=_range_start("today"))
    return templates.TemplateResponse(
        request, "accounting.html", {"request": request, "range": "today", "sources": sources},
    )
