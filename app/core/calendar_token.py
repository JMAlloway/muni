from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer

from app.core.settings import settings

ICAL_SALT = "calendar-feed"
DEFAULT_MAX_AGE_DAYS = 365


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SECRET_KEY, salt=ICAL_SALT)


def make_calendar_token(email: str) -> str:
    return _serializer().dumps({"email": email})


def parse_calendar_token(token: str | None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> str | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=max_age_days * 24 * 3600)
        return (data or {}).get("email")
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None

