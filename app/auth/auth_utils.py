# app/auth_utils.py
from fastapi import Request, HTTPException
from app.auth.session import get_current_user_email


async def require_login(request: Request) -> str:
    """
    Return the current user's email or raise 401 so the global handler can redirect HTML callers.
    """
    email = get_current_user_email(request)
    if email:
        return email
    raise HTTPException(status_code=401, detail="Login required")


async def require_api_user(request: Request) -> str:
    email = get_current_user_email(request)
    if email:
        return email
    raise HTTPException(status_code=401, detail="Not authenticated")
