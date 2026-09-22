# admin_dashboard/dependencies.py
#
# Mirrors webapp/dependencies.py's get_db() pattern: a fresh DatabaseManager
# per request (not a shared global one), since sqlite3 connections are tied
# to the thread that opened them. Deliberately the dashboard's own copy
# rather than a shared import from webapp/ — the two processes are kept
# independent per docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md,
# even though they touch the same underlying ssp_database.db file.

from database.db_manager import DatabaseManager


def get_db():
    db = DatabaseManager()
    try:
        yield db
    finally:
        db.close()
