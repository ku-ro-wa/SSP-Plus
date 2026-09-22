# admin_dashboard/auth.py
#
# Real auth for the Admin Dashboard, replacing the pattern of
# webapp/auth.py's require_admin() stub for this surface. Deliberately
# independent of the touchscreen ADMIN_PIN system (different threat model —
# see CONTEXT.md's "Login session" / "Dashboard admin role" terms and
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md).
#
# Scope note: this covers password hashing and a signed session cookie only
# (issue #13's "happy path"). Sliding inactivity timeout, lockout, and the
# login audit log are a separate ticket (#14) — the cookie here carries no
# expiry of its own yet.

from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from fastapi import Cookie, HTTPException, status
from itsdangerous import BadSignature, URLSafeSerializer

from config import get_config

SESSION_COOKIE_NAME = "dashboard_session"
_SESSION_SALT = "admin-dashboard-session"

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


def create_session_token(username: str, role: str) -> str:
    return _serializer().dumps({"username": username, "role": role})


def read_session_token(token: str) -> Optional[dict]:
    try:
        return _serializer().loads(token)
    except BadSignature:
        return None


def get_current_user(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """FastAPI dependency gating any protected route — raises 401 if there's
    no cookie or its signature doesn't verify."""
    payload = read_session_token(session) if session is not None else None
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return payload
