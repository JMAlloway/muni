# app/session.py

from itsdangerous import TimedSerializer, BadSignature, SignatureExpired
from fastapi import Request
import time

from app.core.settings import settings

SESSION_COOKIE_NAME = "muni_session"
SESSION_SALT = "muni-session"

def _serializer():
    return TimedSerializer(settings.SECRET_KEY, salt=SESSION_SALT)

def create_session_token(email: str, ttl_minutes: int | None = None) -> str:
    # TimedSerializer enforces expiration at loads() time via max_age. We only store email.
    return _serializer().dumps({"email": email})


def parse_session_token(token: str | None, max_age: int | None = None) -> str | None:
    if not token:
        return None
    try:
        max_age_sec = max_age if max_age is not None else int(getattr(settings, "ACCESS_TOKEN_EXPIRES_MIN", 120)) * 60
        data = _serializer().loads(token, max_age=max_age_sec)
        return data.get("email")
    except (SignatureExpired, BadSignature):
        return None

def get_current_user_email(request: Request) -> str | None:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    return parse_session_token(raw)




