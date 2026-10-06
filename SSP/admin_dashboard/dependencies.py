# admin_dashboard/dependencies.py
#
# Mirrors webapp/dependencies.py's get_db() pattern: a fresh DatabaseManager
# per request (not a shared global one), since sqlite3 connections are tied
# to the thread that opened them. Deliberately the dashboard's own copy
# rather than a shared import from webapp/ — the two processes are kept
# independent per docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md,
# even though they touch the same underlying ssp_database.db file.
#
# When SIM_MODE=true, reads/writes go to the demo fixture file
# (database.db_manager.SIM_DB_NAME) seeded by admin_dashboard/seed_demo_data.py
# (issue #18) instead of the real ssp_database.db, so the accounting page can
# be visually checked before the kiosk has accumulated real transactions.

from config import get_config
from database.db_manager import DatabaseManager, SIM_DB_NAME
from database.models import migrate_dashboard_roles


def open_db() -> DatabaseManager:
    """The DatabaseManager for whichever file this process should use — the
    SIM_MODE demo file or the real DB. Shared with admin_dashboard/cli.py so
    accounts it creates land in the same file the dashboard logs in against.

    Runs the one-time role rename itself rather than relying on the kiosk
    app's init_db(): the dashboard and CLI can run against the DB before the
    kiosk app restarts on new code, and must never read an old read-only
    `admin` row as the new privileged `admin`."""
    db = DatabaseManager(db_name=SIM_DB_NAME) if get_config().sim_mode else DatabaseManager()
    if db.conn:
        migrate_dashboard_roles(db.conn)
    return db


def get_db():
    db = open_db()
    try:
        yield db
    finally:
        db.close()
