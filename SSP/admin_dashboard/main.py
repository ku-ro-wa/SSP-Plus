# admin_dashboard/main.py
#
# The Admin Dashboard's own FastAPI app — a sibling process to webapp/main.py
# (the Wi-Fi portal), never sharing a process or lifecycle with it. See
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md for
# why: a bug in the low-trust, unauthenticated Wi-Fi portal must never
# become a path into this DB-write-capable, authenticated surface.
#
# Started via `make run-admin-dashboard`, never spawned by main_app.py.

from fastapi import FastAPI

from config import get_config
from admin_dashboard.routers import auth

config = get_config()

# Mirrors webapp/main.py's reasoning for gating /docs and /redoc off in
# production via the same API_DOCS_ENABLED setting.
docs_url = "/docs" if config.docs_enabled else None
redoc_url = "/redoc" if config.docs_enabled else None

app = FastAPI(title="AIO SPARK Admin Dashboard", docs_url=docs_url, redoc_url=redoc_url)

app.include_router(auth.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.admin_dashboard_port)
