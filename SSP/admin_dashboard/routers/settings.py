# admin_dashboard/routers/settings.py
#
# Issue #106: the runtime settings from managers/settings_catalog.py. Both
# dashboard roles can read them; only `admin` can save. The kiosk reads each
# key from the DB at the moment it uses it, so a save needs no restart.

from typing import Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from admin_dashboard.auth import WRITE_ROLE, get_current_user, get_current_user_page, require_write_role
from admin_dashboard.dependencies import get_db
from managers.admin_actions import WHERE_DASHBOARD, record_setting_changes
from admin_dashboard.templating import templates
from managers.settings_catalog import (
    CATALOG, DASHBOARD, get_value, save_many, settings_for,
)

router = APIRouter()


class SettingsUpdate(BaseModel):
    values: Dict[str, object]


def build_settings(db):
    return [
        {
            "key": s.key, "label": s.label, "unit": s.unit, "help": s.help,
            "minimum": s.minimum, "maximum": s.maximum, "default": s.default,
            "value": get_value(db, s.key),
        }
        for s in settings_for(DASHBOARD)
    ]


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    current_user: dict = Depends(get_current_user_page),
    db=Depends(get_db),
):
    return templates.TemplateResponse(
        request, "settings.html",
        {
            "request": request, "active": "settings",
            "settings": build_settings(db),
            "can_edit": current_user["role"] == WRITE_ROLE,
        },
    )


@router.get("/settings/data")
def settings_data(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    return {"settings": build_settings(db)}


@router.post("/settings")
def settings_save(
    request: Request,
    body: SettingsUpdate,
    current_user: dict = Depends(require_write_role),
    db=Depends(get_db),
):
    """Save one or more settings. All values are checked first and nothing is
    written unless every one is valid: a 422 lists a message per bad key."""
    keys = {s.key for s in CATALOG}
    old = {key: get_value(db, key) for key in body.values if key in keys}
    cleaned, errors = save_many(db, body.values, surface=DASHBOARD)
    if errors:
        return JSONResponse({"errors": errors}, status_code=422)
    record_setting_changes(
        db, old, cleaned, actor=current_user["username"], where=WHERE_DASHBOARD,
        ip=request.client.host if request.client else None,
    )
    return {"saved": cleaned}
