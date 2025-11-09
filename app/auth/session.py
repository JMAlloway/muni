# app/session.py

from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Request

from app.core.settings import settings

SESSION_COOKIE_NAME = "muni_session"
SESSION_SALT = "muni-session"

def _serializer():
    return URLSafeSerializer(settings.SECRET_KEY, salt=SESSION_SALT)

def create_session_token(email: str) -> str:
    return _serializer().dumps({"email": email})

def parse_session_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token)
        return data.get("email")
    except BadSignature:
        return None

def get_current_user_email(request: Request) -> str | None:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    return parse_session_token(raw)
