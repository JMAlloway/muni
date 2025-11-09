"""Compatibility shim for authentication helpers."""

from app.auth.auth_utils import require_api_user, require_login

__all__ = ["require_api_user", "require_login"]
