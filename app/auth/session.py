# app/session.py

from itsdangerous import TimedSerializer, BadSignature, SignatureExpired
from fastapi import Request

from app.core.settings import settings

SESSION_COOKIE_NAME = "muni_session"
SESSION_SALT = "muni-session"

def _serializer() -> TimedSerializer:
    return TimedSerializer(settings.SECRET_KEY, salt=SESSION_SALT)

def create_session_token(email: str) -> str:
    # Expiration is enforced at loads() time; token just stores data.
    return _serializer().dumps({"email": email})

def parse_session_token(token: str | None, max_age_minutes: int | None = None) -> str | None:
    if not token:
        return None
    try:
        # If not provided, fall back to settings value (minutes -> seconds)
        minutes = max_age_minutes if max_age_minutes is not None else int(
            getattr(settings, "ACCESS_TOKEN_EXPIRES_MIN", 120)
        )
        max_age_sec = minutes * 60

        data = _serializer().loads(token, max_age=max_age_sec)
        return data.get("email")
    except (SignatureExpired, BadSignature):
        return None

def get_current_user_email(request: Request) -> str | None:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    return parse_session_token(raw)
