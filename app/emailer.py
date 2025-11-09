"""Backward-compatible import for email utilities."""

from app.core.emailer import send_email

__all__ = ["send_email"]
