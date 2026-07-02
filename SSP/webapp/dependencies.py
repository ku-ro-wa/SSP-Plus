# webapp/dependencies.py
#
# FastAPI "dependencies" are functions you Depends() on in a route signature;
# FastAPI calls them per-request and injects the return value as an argument.
# get_db() is the shared DB access point every route below will use instead
# of importing DatabaseManager directly.

from database.db_manager import DatabaseManager


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
