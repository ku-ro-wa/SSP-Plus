# admin_dashboard/auth.py
#
# Real auth for the Admin Dashboard, replacing the pattern of
# webapp/auth.py's require_admin() stub for this surface. Deliberately
# independent of the touchscreen ADMIN_PIN system (different threat model —
# see CONTEXT.md's "Login session" / "Dashboard admin role" terms and
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md).
#
# Covers password hashing, a signed session cookie with a sliding inactivity
# timeout, and consecutive-failed-attempt account lockout (issue #14, on top
# of #13's happy path).

import time
from datetime import datetime, timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from fastapi import Cookie, Depends, HTTPException, Response, status
from itsdangerous import BadSignature, URLSafeSerializer

from config import get_config

SESSION_COOKIE_NAME = "dashboard_session"
_SESSION_SALT = "admin-dashboard-session"

# Fixed by issue #14's acceptance criteria (not configurable, unlike the
# lockout duration itself).
FAILED_ATTEMPTS_LOCKOUT_THRESHOLD = 5

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_config().admin_dashboard_secret_key, salt=_SESSION_SALT)


def create_session_token(username: str, role: str, last_activity: Optional[float] = None) -> str:
    """`last_activity` is a Unix timestamp; defaults to now. Callers only
    pass it explicitly to construct a backdated token (tests exercising
    sliding-timeout expiry)."""
    if last_activity is None:
        last_activity = time.time()
    return _serializer().dumps({"username": username, "role": role, "last_activity": last_activity})


def read_session_token(token: str) -> Optional[dict]:
    try:
        return _serializer().loads(token)
    except BadSignature:
        return None


def _session_expired(payload: dict) -> bool:
    last_activity = payload.get("last_activity")
    if last_activity is None:
        return True
    timeout_seconds = get_config().admin_dashboard_session_hours * 3600
    return (time.time() - last_activity) > timeout_seconds


def get_current_user(
    response: Response,
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """FastAPI dependency gating any protected route — raises 401 if there's
    no cookie, its signature doesn't verify, or the sliding 10-hour
    inactivity timeout has elapsed. Any successful call is itself "activity",
    so it reissues the cookie with a refreshed last-activity time, sliding
    the countdown forward."""
    payload = read_session_token(session) if session is not None else None
    if payload is None or _session_expired(payload):
        response.delete_cookie(SESSION_COOKIE_NAME)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(payload["username"], payload["role"]),
        httponly=True,
        samesite="lax",
    )
    return {"username": payload["username"], "role": payload["role"]}


class LoginRequired(Exception):
    """Raised by get_current_user_page instead of a 401, so main.py's
    exception handler can redirect a browser to the /login form rather than
    showing it a bare JSON error."""


def get_current_user_page(
    response: Response,
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """get_current_user for HTML page routes — same checks and sliding
    refresh, but an unauthenticated request raises LoginRequired (a redirect
    to /login) instead of 401. JSON endpoints keep using get_current_user."""
    try:
        return get_current_user(response, session)
    except HTTPException:
        raise LoginRequired()


def require_dev(current_user: dict = Depends(get_current_user)) -> dict:
    """Role-gating dependency for write actions the read-only `admin` role
    must not reach (issue #17's paper-count reset). Layers on top of
    get_current_user, so an unauthenticated request still gets 401 before
    the role check ever runs — only an authenticated non-`dev` user gets
    403."""
    if current_user["role"] != "dev":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires the dev role")
    return current_user


def is_locked_out(user: dict) -> bool:
    """Whether `user` (a row from get_user_by_username) is currently within
    its failed-attempt lockout window."""
    locked_until = user.get("locked_until")
    if not locked_until:
        return False
    if isinstance(locked_until, str):
        locked_until = datetime.fromisoformat(locked_until)
    return datetime.now() < locked_until


def register_failed_attempt(db, username: str) -> None:
    """Increment the consecutive-failed-attempt counter for `username`, and
    lock the account if it just reached the threshold."""
    new_count = db.increment_failed_login_attempts(username)
    if new_count is not None and new_count >= FAILED_ATTEMPTS_LOCKOUT_THRESHOLD:
        locked_until = datetime.now() + timedelta(minutes=get_config().admin_dashboard_lockout_minutes)
        db.set_account_lock(username, locked_until)


def register_successful_login(db, username: str) -> None:
    """Clear the failed-attempt counter and any lock — a successful login
    always resets lockout state."""
    db.reset_failed_login_attempts(username)
