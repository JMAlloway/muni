# app/auth_utils.py
from fastapi import Request
from fastapi.responses import RedirectResponse
from app.session import get_current_user_email

async def require_login(request: Request):
    """Redirect to /login if not authenticated."""
    email = get_current_user_email(request)
    if not email:
        return RedirectResponse(url="/login", status_code=303)
    return email
