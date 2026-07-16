# webapp/dependencies.py
#
# FastAPI "dependencies" are functions you Depends() on in a route signature;
# FastAPI calls them per-request and injects the return value as an argument.
# get_db() is the shared DB access point every route below will use instead
# of importing DatabaseManager directly.

from config import get_config
from database.db_manager import DatabaseManager
from managers.adapters.wifi_adapter import WifiAdapter
from managers.session_manager import SessionManager


def get_db():
    # A fresh connection per request, not a shared global one: sqlite3
    # connections are tied to the thread that opened them, and Starlette
    # runs sync routes across a threadpool, so reusing one connection here
    # would trip the same cross-thread restriction db_threader exists to
    # avoid on the PyQt side.
    db = DatabaseManager()
    try:
        yield db
    finally:
        db.close()


def get_wifi_adapter():
    # Built on its own DatabaseManager (not get_db()) for the same
    # per-request/per-thread connection reason as above.
    db = DatabaseManager()
    try:
        config = get_config()
        session_manager = SessionManager(db)
        yield WifiAdapter(
            session_manager=session_manager,
            upload_dir=config.wifi_upload_dir,
            max_size_bytes=config.max_upload_size_mb * 1024 * 1024,
        )
    finally:
        db.close()
