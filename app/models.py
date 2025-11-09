"""Compatibility wrapper for ORM entities.

Existing imports like ``from app.models import User`` continue to work,
while the canonical definitions live in :mod:`app.domain.models`.
"""

from app.domain.models import Base, Opportunity, Preference, User

__all__ = ["Base", "Opportunity", "Preference", "User"]
