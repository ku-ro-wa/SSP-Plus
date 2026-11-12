# admin_dashboard/routers/kiosk.py
#
# Release 1 of docs/adr/0005: read-only /kiosk (supplies, reader, last seen)
# and /logs (transactions, cash inventory, error log), each with a JSON twin.
# Reachable by either dashboard role; nothing here writes.

from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from admin_dashboard.auth import WRITE_ROLE, get_current_user, get_current_user_page, require_write_role
from admin_dashboard.dependencies import get_db
from admin_dashboard.kiosk_overview import build_overview
from admin_dashboard.templating import templates
from managers import inventory_edits as edits
from managers.log_pages import (
    ERROR_COLUMNS, NUMERIC_COLUMNS, PAGE_SIZE, TRANSACTION_COLUMNS, page_count,
)

router = APIRouter()


def _page(rows_and_total, page):
    rows, total = rows_and_total
    pages = page_count(total)
    return {"rows": rows, "page": page, "pages": pages, "total": total}


def build_logs(db, tx_page, err_page, act_page=1):
    return {
        "page_size": PAGE_SIZE,
        "columns": {"transactions": list(TRANSACTION_COLUMNS), "errors": list(ERROR_COLUMNS),
                    "numeric": list(NUMERIC_COLUMNS)},
        "transactions": _page(db.get_transaction_page(PAGE_SIZE, (tx_page - 1) * PAGE_SIZE), tx_page),
        "cash": db.get_cash_inventory(),
        "errors": _page(db.get_error_page(PAGE_SIZE, (err_page - 1) * PAGE_SIZE), err_page),
        "actions": _page(db.get_admin_action_page(PAGE_SIZE, (act_page - 1) * PAGE_SIZE), act_page),
    }


def edit_limits():
    """The ranges and refill values the page shows beside its controls."""
    return {
        "paper_max": edits.PAPER_FULL, "coin_max": edits.COIN_MAX,
        "coin_refill": edits.COIN_REFILL, "ink_max": edits.INK_FULL,
    }


@router.get("/kiosk", response_class=HTMLResponse)
def kiosk_page(
    request: Request,
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    return templates.TemplateResponse(
        request, "kiosk.html",
        {
            "request": request, "active": "kiosk", "o": build_overview(db),
            "can_edit": current_user["role"] == WRITE_ROLE,
            "limits": edit_limits(),
        },
    )


@router.get("/kiosk/data")
def kiosk_data(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    return build_overview(db)


@router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    tx_page: int = Query(1, ge=1),
    err_page: int = Query(1, ge=1),
    act_page: int = Query(1, ge=1),
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    return templates.TemplateResponse(
        request, "logs.html",
        {"request": request, "active": "logs", "logs": build_logs(db, tx_page, err_page, act_page)},
    )


@router.get("/logs/data")
def logs_data(
    tx_page: int = Query(1, ge=1),
    err_page: int = Query(1, ge=1),
    act_page: int = Query(1, ge=1),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    return build_logs(db, tx_page, err_page, act_page)


# ------------------------------------------------------------------- edits
#
# Issue #135 (ADR 0005, Release 2): the edits Kiosk Admin offers, for the `admin`
# role only (`require_write_role`: 401 unauthenticated, 403 for `operator`). Each
# goes through managers/inventory_edits.py, the code the touchscreen uses, so the
# ranges are the same and each change writes an `admin_actions` row.


def _who(request, user):
    return edits.dashboard_actor(user["username"], request.client.host if request.client else None)


def _refused(error):
    return JSONResponse({"error": str(error)}, status_code=422)


class PaperEdit(BaseModel):
    count: object


class CoinsEdit(BaseModel):
    peso_1: Optional[object] = None
    peso_5: Optional[object] = None


class InkEdit(BaseModel):
    levels: Dict[str, object]


class CollectCash(BaseModel):
    expected_total: Optional[float] = None


@router.post("/kiosk/paper")
def set_paper(body: PaperEdit, request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    try:
        count = edits.parse_paper(body.count)
    except edits.EditError as e:
        return _refused(e)
    edits.set_paper(db, count, _who(request, user))
    return {"paper_count": count}


@router.post("/kiosk/paper/refill")
def refill_paper(request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    edits.set_paper(db, edits.PAPER_FULL, _who(request, user))
    return {"paper_count": edits.PAPER_FULL}


@router.post("/kiosk/coins")
def set_coins(body: CoinsEdit, request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    given = {1: body.peso_1, 5: body.peso_5}
    if all(v is None for v in given.values()):
        return _refused("Enter a count for at least one hopper.")
    try:  # check both before writing either
        counts = {d: edits.parse_coin_count(v, d) for d, v in given.items() if v is not None}
    except edits.EditError as e:
        return _refused(e)
    for denomination, count in counts.items():
        edits.set_coin_count(db, denomination, count, _who(request, user))
    current = edits.current_coins(db)
    return {"peso_1": current[1], "peso_5": current[5]}


@router.post("/kiosk/coins/refill")
def refill_coins(request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    done = edits.refill_coins(db, _who(request, user))
    return {"peso_1": done[1], "peso_5": done[5]}


@router.post("/kiosk/ink")
def set_ink(body: InkEdit, request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    try:
        levels = edits.check_ink(body.levels)
        edits.set_ink(db, levels, _who(request, user))
    except edits.EditError as e:
        return _refused(e)
    return {"levels": levels}


@router.post("/kiosk/ink/refill")
def refill_ink(request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    try:
        levels = edits.refill_ink(db, _who(request, user))
    except edits.EditError as e:
        return _refused(e)
    return {"levels": levels}


@router.get("/kiosk/collect-cash/preview")
def collect_cash_preview(user: dict = Depends(require_write_role), db=Depends(get_db)):
    """What a collection would record right now: the touchscreen's confirmation figures."""
    return db.get_collection_preview()


@router.post("/kiosk/collect-cash")
def collect_cash(body: CollectCash, request: Request, user: dict = Depends(require_write_role), db=Depends(get_db)):
    """Record the collection and zero the counts. `expected_total` is the total the
    operator confirmed; if the counts have moved since, nothing is collected (409)."""
    try:
        collection_id = edits.collect_cash(db, _who(request, user), body.expected_total)
    except edits.CollectionChanged as e:
        return JSONResponse({"error": str(e), "preview": e.preview}, status_code=409)
    except edits.EditError as e:
        return _refused(e)
    return {"collection_id": collection_id}
