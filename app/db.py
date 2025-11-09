"""Compatibility module exposing database session helpers.

This wrapper keeps legacy imports like ``from app.db import get_session``
functioning while the codebase migrates to :mod:`app.core.db`.
"""

from app.core.db import AsyncSessionLocal, engine, get_session

__all__ = ["AsyncSessionLocal", "engine", "get_session"]
