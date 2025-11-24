import uuid
from urllib.parse import quote_plus

from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer

from app.core.settings import settings

UNSUB_SALT = "digest-unsubscribe"
DEFAULT_MAX_AGE_DAYS = 180


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SECRET_KEY, salt=UNSUB_SALT)


def make_unsubscribe_token(email: str) -> str:
    """Return a signed token embedding the email address."""
    return _serializer().dumps({"email": email})


def parse_unsubscribe_token(token: str | None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> str | None:
    """Validate token and return email, or None if invalid/expired."""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=max_age_days * 24 * 3600)
        return (data or {}).get("email")
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None


def build_unsubscribe_url(email: str) -> str:
    base = getattr(settings, "PUBLIC_APP_URL", "http://localhost:8000").rstrip("/")
    token = make_unsubscribe_token(email)
    return f"{base}/unsubscribe?token={quote_plus(token)}&email={quote_plus(email)}"

