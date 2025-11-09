"""Authentication utilities exposed at the package level."""

from .auth import (
    create_admin_if_missing,
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from .session import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_current_user_email,
    parse_session_token,
)
from .auth_utils import require_login, require_api_user

__all__ = [
    "create_admin_if_missing",
    "create_token",
    "get_current_user",
    "hash_password",
    "require_admin",
    "verify_password",
    "SESSION_COOKIE_NAME",
    "create_session_token",
    "get_current_user_email",
    "parse_session_token",
    "require_login",
    "require_api_user",
]
