# app/auth_utils.py
from __future__ import annotations
from urllib.parse import urlencode
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from app.session import get_current_user_email

def _build_next_query(request: Request) -> str:
    dest = request.url.path
    if request.url.query:
        dest += "?" + request.url.query
    if not dest or dest.startswith("/login"):
        return ""  # never point next back to /login
    return "?" + urlencode({"next": dest})

def login_redirect(request: Request) -> RedirectResponse:
    """303 redirect to /login?next=... (never points next to /login)."""
    return RedirectResponse("/login" + _build_next_query(request), status_code=303)

async def require_login(request: Request) -> str | RedirectResponse:
    """
    Use in HTML page routes. Returns email or a RedirectResponse.
    Never points back to /login as next target (prevents ping-pong).
    """
    email = get_current_user_email(request)
    if email:
        return email
    return login_redirect(request)

async def require_api_user(request: Request) -> str:
    """Use in JSON/API routes. Raises 401 for JS to handle."""
    email = get_current_user_email(request)
    if email:
        return email
    raise HTTPException(status_code=401, detail="Not authenticated")
