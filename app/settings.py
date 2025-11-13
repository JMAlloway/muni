"""Compatibility shim for the global Settings instance."""

from app.core.settings import Settings, settings

__all__ = ["Settings", "settings"]

