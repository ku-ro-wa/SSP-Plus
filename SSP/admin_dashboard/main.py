# admin_dashboard/main.py
#
# The Admin Dashboard's own FastAPI app — a sibling process to webapp/main.py
# (the Wi-Fi portal), never sharing a process or lifecycle with it. See
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md for
# why: a bug in the low-trust, unauthenticated Wi-Fi portal must never
# become a path into this DB-write-capable, authenticated surface.
#
# Started via `make run-admin-dashboard`, never spawned by main_app.py.

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import get_config
from admin_dashboard.auth import SESSION_COOKIE_NAME, LoginRequired
from admin_dashboard.startup_check import secret_key_problem
from admin_dashboard.routers import accounting, auth, kiosk

config = get_config()

# Mirrors webapp/main.py's reasoning for gating /docs and /redoc off in
# production via the same API_DOCS_ENABLED setting.
docs_url = "/docs" if config.docs_enabled else None
redoc_url = "/redoc" if config.docs_enabled else None

app = FastAPI(title="AIO SPARK Admin Dashboard", docs_url=docs_url, redoc_url=redoc_url)

app.include_router(auth.router)
app.include_router(accounting.router)
app.include_router(kiosk.router)


@app.get("/", include_in_schema=False)
def root():
    # /kiosk is the landing page: is the kiosk up, and does it need anything?
    return RedirectResponse("/kiosk")


@app.exception_handler(LoginRequired)
def redirect_to_login(request: Request, exc: LoginRequired):
    """HTML pages (via get_current_user_page) send an unauthenticated
    browser to the sign-in form instead of a JSON 401, clearing any stale or
    expired cookie on the way."""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# Serves the dashboard's own vendored static files (e.g. static/js/chart.umd.min.js,
# issue #16) at /static/... — a local copy, not a CDN fetch, consistent with
# this being a local-first, possibly-offline surface.
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def main():
    """Start the server, refusing a forgeable cookie-signing key outside SIM_MODE."""
    problem = secret_key_problem(config)
    if problem:
        print(f"Admin Dashboard not started: {problem}", file=sys.stderr)
        return 1

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.admin_dashboard_port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
