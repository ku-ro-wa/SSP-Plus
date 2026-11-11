# admin_dashboard/routers/kiosk.py
#
# Release 1 of docs/adr/0005: read-only /kiosk (supplies, reader, last seen)
# and /logs (transactions, cash inventory, error log), each with a JSON twin.
# Reachable by either dashboard role; nothing here writes.

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from admin_dashboard.auth import get_current_user, get_current_user_page
from admin_dashboard.dependencies import get_db
from admin_dashboard.kiosk_overview import build_overview
from admin_dashboard.templating import templates
from managers.log_pages import (
    ERROR_COLUMNS, NUMERIC_COLUMNS, PAGE_SIZE, TRANSACTION_COLUMNS, page_count,
)

router = APIRouter()


def _page(rows_and_total, page):
    rows, total = rows_and_total
    pages = page_count(total)
    return {"rows": rows, "page": page, "pages": pages, "total": total}


def build_logs(db, tx_page, err_page):
    return {
        "page_size": PAGE_SIZE,
        "columns": {"transactions": list(TRANSACTION_COLUMNS), "errors": list(ERROR_COLUMNS),
                    "numeric": list(NUMERIC_COLUMNS)},
        "transactions": _page(db.get_transaction_page(PAGE_SIZE, (tx_page - 1) * PAGE_SIZE), tx_page),
        "cash": db.get_cash_inventory(),
        "errors": _page(db.get_error_page(PAGE_SIZE, (err_page - 1) * PAGE_SIZE), err_page),
    }


@router.get("/kiosk", response_class=HTMLResponse)
def kiosk_page(
    request: Request,
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    return templates.TemplateResponse(
        request, "kiosk.html",
        {"request": request, "active": "kiosk", "o": build_overview(db)},
    )


@router.get("/kiosk/data")
def kiosk_data(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    return build_overview(db)


@router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    tx_page: int = Query(1, ge=1),
    err_page: int = Query(1, ge=1),
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    return templates.TemplateResponse(
        request, "logs.html",
        {"request": request, "active": "logs", "logs": build_logs(db, tx_page, err_page)},
    )


@router.get("/logs/data")
def logs_data(
    tx_page: int = Query(1, ge=1),
    err_page: int = Query(1, ge=1),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    return build_logs(db, tx_page, err_page)
