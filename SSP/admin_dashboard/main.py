# admin_dashboard/main.py
#
# The Admin Dashboard's own FastAPI app — a sibling process to webapp/main.py
# (the Wi-Fi portal), never sharing a process or lifecycle with it. See
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md for
# why: a bug in the low-trust, unauthenticated Wi-Fi portal must never
# become a path into this DB-write-capable, authenticated surface.
#
# Started via `make run-admin-dashboard`, never spawned by main_app.py.

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import get_config
from admin_dashboard.routers import accounting, auth

config = get_config()

# Mirrors webapp/main.py's reasoning for gating /docs and /redoc off in
# production via the same API_DOCS_ENABLED setting.
docs_url = "/docs" if config.docs_enabled else None
redoc_url = "/redoc" if config.docs_enabled else None

app = FastAPI(title="AIO SPARK Admin Dashboard", docs_url=docs_url, redoc_url=redoc_url)

app.include_router(auth.router)
app.include_router(accounting.router)

# Serves the dashboard's own vendored static files (e.g. static/js/chart.umd.min.js,
# issue #16) at /static/... — a local copy, not a CDN fetch, consistent with
# this being a local-first, possibly-offline surface.
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.admin_dashboard_port)
