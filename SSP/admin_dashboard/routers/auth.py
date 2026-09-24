# admin_dashboard/routers/auth.py
#
# /login verifies credentials against the users table and issues the signed
# Login session cookie; /me is the minimal protected endpoint issue #13
# asks for — just enough to prove the cookie actually gates access and
# reflects who's logged in. Issue #14 adds lockout after 5 consecutive
# failed attempts and a login audit log row for every attempt. GET /login
# serves the browser sign-in form, which posts JSON to POST /login.

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from admin_dashboard.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_current_user,
    is_locked_out,
    register_failed_attempt,
    register_successful_login,
    verify_password,
)
from admin_dashboard.dependencies import get_db

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request})


@router.post("/login")
def login(credentials: LoginRequest, request: Request, response: Response, db=Depends(get_db)):
    source_ip = request.client.host if request.client else None

    def reject(detail: str):
        db.record_login_attempt(credentials.username, False, source_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    user = db.get_user_by_username(credentials.username)

    # A locked-out account is rejected outright, without verifying the
    # password — correct credentials don't bypass the lockout window.
    if user is not None and is_locked_out(user):
        reject("Account is temporarily locked due to repeated failed login attempts")

    if user is None or not verify_password(credentials.password, user["password_hash"]):
        if user is not None:
            register_failed_attempt(db, user["username"])
        reject("Invalid username or password")

    register_successful_login(db, user["username"])
    db.record_login_attempt(credentials.username, True, source_ip)

    token = create_session_token(user["username"], user["role"])
    response.set_cookie(key=SESSION_COOKIE_NAME, value=token, httponly=True, samesite="lax")
    return {"username": user["username"], "role": user["role"]}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user
