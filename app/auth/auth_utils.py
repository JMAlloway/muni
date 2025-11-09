# app/auth_utils.py
from fastapi import Request, HTTPException

from app.auth.session import get_current_user_email

async def require_login(request: Request) -> str:
    # Keep for other routes if you want, but dashboard no longer relies on it
    email = get_current_user_email(request)
    if email:
        return email
    # 403 avoids your global 401 → login redirect loop
    raise HTTPException(status_code=403, detail="Login required")

async def require_api_user(request: Request) -> str:
    email = get_current_user_email(request)
    if email:
        return email
    raise HTTPException(status_code=401, detail="Not authenticated")
