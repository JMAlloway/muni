from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.core.db_core import engine
from app.onboarding.interests import (
    DEFAULT_INTEREST_KEY,
    get_interest_profile,
)

STEP_ORDER = {
    "signup": 0,
    "browsing": 1,
    "tracked_first": 2,
    "completed": 3,
}


async def get_onboarding_state(email: str) -> Dict[str, Any]:
    """Return primary interest + onboarding progress for a user."""
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT primary_interest, onboarding_step, onboarding_completed
            FROM users
            WHERE email = :email
            LIMIT 1
            """,
            {"email": email},
        )
        row = res.first()

    if not row:
        return {
            "primary_interest": DEFAULT_INTEREST_KEY,
            "onboarding_step": "signup",
            "onboarding_completed": False,
        }

    data = row._mapping
    return {
        "primary_interest": (data.get("primary_interest") or DEFAULT_INTEREST_KEY),
        "onboarding_step": (data.get("onboarding_step") or "signup"),
        "onboarding_completed": bool(data.get("onboarding_completed") or False),
    }


async def set_primary_interest(email: str, interest_key: str) -> None:
    """Persist the user-selected interest and seed smart defaults."""
    profile = get_interest_profile(interest_key)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            UPDATE users
            SET primary_interest = :interest
            WHERE email = :email
            """,
            {"interest": profile["key"], "email": email},
        )

    await ensure_default_preferences(email, profile["key"])


async def ensure_default_preferences(email: str, interest_key: str) -> None:
    """Create or backfill user_preferences when nothing is saved yet."""
    profile = get_interest_profile(interest_key)
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT agencies, frequency
            FROM user_preferences
            WHERE user_email = :email
            LIMIT 1
            """,
            {"email": email},
        )
        row = res.first()

    needs_agencies = True
    needs_frequency = True
    if row:
        agencies_raw = row[0] or ""
        freq_raw = (row[1] or "").strip()
        needs_agencies = agencies_raw in ("", "[]", None)
        needs_frequency = not freq_raw

    if not needs_agencies and not needs_frequency:
        return

    agencies_json = json.dumps(profile["default_agencies"])
    freq_val = profile["default_frequency"]

    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            INSERT INTO user_preferences (user_email, agencies, keywords, frequency, created_at, updated_at)
            VALUES (:email, :agencies, '[]', :frequency, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_email) DO UPDATE SET
                agencies = CASE
                    WHEN :needs_agencies = 1 THEN excluded.agencies
                    ELSE user_preferences.agencies
                END,
                frequency = CASE
                    WHEN :needs_frequency = 1 THEN excluded.frequency
                    ELSE user_preferences.frequency
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            {
                "email": email,
                "agencies": agencies_json,
                "frequency": freq_val,
                "needs_agencies": 1 if needs_agencies else 0,
                "needs_frequency": 1 if needs_frequency else 0,
            },
        )


async def record_milestone(
    email: str,
    step: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Record an onboarding milestone event and update the user's progress.
    Returns True if the user's onboarding_step advanced.
    """
    normalized = (step or "").strip().lower()
    if normalized not in STEP_ORDER:
        return False

    meta_json = json.dumps(metadata or {})
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            INSERT INTO user_onboarding_events (user_email, step, metadata)
            VALUES (:email, :step, :metadata)
            """,
            {"email": email, "step": normalized, "metadata": meta_json},
        )

        res = await conn.exec_driver_sql(
            """
            SELECT onboarding_step, onboarding_completed
            FROM users
            WHERE email = :email
            LIMIT 1
            """,
            {"email": email},
        )
        row = res.first()
        if not row:
            return False

        current = (row[0] or "signup").strip().lower()
        current_rank = STEP_ORDER.get(current, -1)
        desired_rank = STEP_ORDER[normalized]
        advanced = desired_rank > current_rank

        updates = []
        params: Dict[str, Any] = {"email": email}

        if advanced:
            updates.append("onboarding_step = :step_val")
            params["step_val"] = normalized

        if normalized == "tracked_first":
            updates.append("first_tracked_at = COALESCE(first_tracked_at, CURRENT_TIMESTAMP)")
            if current_rank < STEP_ORDER["tracked_first"]:
                # make sure we don't get stuck before tracked_first
                if "step_val" not in params:
                    params["step_val"] = "tracked_first"
                if "onboarding_step = :step_val" not in updates:
                    updates.append("onboarding_step = :step_val")

        if normalized == "completed":
            updates.append("onboarding_completed = 1")
            params.setdefault("step_val", "completed")
            if "onboarding_step = :step_val" not in updates:
                updates.append("onboarding_step = :step_val")

        if updates:
            await conn.exec_driver_sql(
                f"UPDATE users SET {', '.join(updates)} WHERE email = :email",
                params,
            )

    return advanced


async def mark_onboarding_completed(
    email: str, metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Convenience helper to close out onboarding."""
    return await record_milestone(email, "completed", metadata)
