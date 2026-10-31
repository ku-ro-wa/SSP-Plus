# admin_dashboard/routers/kiosk.py
#
# Release 1 of docs/adr/0005: read-only /kiosk (supplies, reader, last seen)
# and /logs (transactions, cash inventory, error log). Reachable by either
# dashboard role; nothing here writes.

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from admin_dashboard.auth import get_current_user, get_current_user_page
from admin_dashboard.dependencies import get_db
from admin_dashboard.kiosk_overview import build_overview

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

LOG_ROWS = 100


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
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    return templates.TemplateResponse(
        request, "logs.html",
        {
            "request": request,
            "active": "logs",
            "transactions": db.get_transaction_history()[:LOG_ROWS],
            "cash": db.get_cash_inventory(),
            "errors": db.get_error_log()[:LOG_ROWS],
            "limit": LOG_ROWS,
        },
    )
