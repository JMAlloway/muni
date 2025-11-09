"""Legacy compatibility wrapper for bulk database utilities.

Modules that still import ``app.db_core`` will resolve to the new
implementation in :mod:`app.core.db_core`.
"""

from app.core.db_core import engine, metadata, opportunities, save_opportunities

__all__ = [
    "engine",
    "metadata",
    "opportunities",
    "save_opportunities",
]
