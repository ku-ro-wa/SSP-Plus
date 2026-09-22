# admin_dashboard/routers/auth.py
#
# /login verifies credentials against the users table and issues the signed
# Login session cookie; /me is the minimal protected endpoint issue #13
# asks for — just enough to prove the cookie actually gates access and
# reflects who's logged in.

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from admin_dashboard.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_current_user,
    verify_password,
)
from admin_dashboard.dependencies import get_db

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(credentials: LoginRequest, response: Response, db=Depends(get_db)):
    user = db.get_user_by_username(credentials.username)
    if user is None or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_session_token(user["username"], user["role"])
    response.set_cookie(key=SESSION_COOKIE_NAME, value=token, httponly=True, samesite="lax")
    return {"username": user["username"], "role": user["role"]}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user
