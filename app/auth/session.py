# app/session.py

from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Request
import time

from app.core.settings import settings

SESSION_COOKIE_NAME = "muni_session"
SESSION_SALT = "muni-session"

def _serializer():
    return URLSafeSerializer(settings.SECRET_KEY, salt=SESSION_SALT)

def create_session_token(email: str, ttl_minutes: int | None = None) -> str:
    ttl = ttl_minutes if ttl_minutes is not None else settings.ACCESS_TOKEN_EXPIRES_MIN
    exp = int(time.time()) + int(ttl) * 60
    return _serializer().dumps({"email": email, "exp": exp})

def parse_session_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token)
        exp = data.get("exp")
        if isinstance(exp, int) and exp < int(time.time()):
            return None
        return data.get("email")
    except BadSignature:
        return None

def get_current_user_email(request: Request) -> str | None:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    return parse_session_token(raw)
