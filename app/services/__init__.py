"""Application-level service helpers."""

from .onboarding import (
    ensure_default_preferences,
    get_onboarding_state,
    mark_onboarding_completed,
    record_milestone,
    set_primary_interest,
)
from .opportunity_feed import (
    fetch_interest_feed,
    fetch_landing_snapshot,
    get_top_agencies,
)

__all__ = [
    "ensure_default_preferences",
    "get_onboarding_state",
    "mark_onboarding_completed",
    "record_milestone",
    "set_primary_interest",
    "fetch_interest_feed",
    "fetch_landing_snapshot",
    "get_top_agencies",
]
