# app/routers/dev_auth.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, PlainTextResponse
from urllib.parse import quote
from app.auth.session import create_session_token, get_current_user_email, SESSION_COOKIE_NAME

router = APIRouter(prefix="/dev", tags=["dev"])

@router.get("/whoami", response_class=PlainTextResponse)
def whoami(request: Request):
    return (get_current_user_email(request) or "None")

@router.get("/login")
def dev_login(email: str = "admin@example.com", next: str = "/"):
    """
    DEV ONLY: sets a session cookie and redirects to ?next=...
    Use this to prove cookies+redirects work without the password form.
    """
    token = create_session_token(email.strip().lower())
    resp = RedirectResponse(url=next or "/", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,   # True on HTTPS
        samesite="lax",
        path="/",
        max_age=60*60*24*30,
    )
    return resp

@router.get("/logout")
def dev_logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return resp
