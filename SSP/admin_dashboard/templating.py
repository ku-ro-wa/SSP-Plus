# admin_dashboard/templating.py
#
# One Jinja environment for every page, so the shared layout (base.html) can
# show this kiosk's KIOSK_ID without each router passing it in.

from pathlib import Path

from fastapi.templating import Jinja2Templates

from config import get_config

templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.globals["kiosk_id"] = get_config().kiosk_id
