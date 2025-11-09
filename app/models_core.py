"""Compatibility shim for SQLAlchemy Core table definitions."""

from app.core.models_core import metadata, opportunities

__all__ = ["metadata", "opportunities"]
