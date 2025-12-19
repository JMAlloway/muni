from fastapi import HTTPException, Request

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.company_profile_template import merge_company_profile_defaults


async def require_user_with_team(request: Request) -> dict:
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT id, email, team_id FROM users WHERE email = :e LIMIT 1",
            {"e": email},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    m = row._mapping
    return {"id": m["id"], "email": m["email"], "team_id": m.get("team_id")}


async def ensure_user_can_access_opportunity(user: dict, opportunity_id: str) -> None:
    """
    Require that the current user (or their team) tracks this opportunity.
    Falls back to allowing if the opportunity exists and no tracking is required.
    """
    # First check existence
    exists = False
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT COUNT(1) FROM opportunities WHERE id = :oid LIMIT 1",
            {"oid": opportunity_id},
        )
        exists = (res.scalar() or 0) > 0
    if not exists:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Check tracking
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT COUNT(1)
            FROM user_bid_trackers
            WHERE opportunity_id = :oid
              AND (user_id = :uid OR (:team_id IS NOT NULL AND team_id = :team_id))
            """,
            {"oid": opportunity_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        tracked = (res.scalar() or 0) > 0
    if not tracked:
        # Enforce access: user must be tracking the opportunity
        raise HTTPException(status_code=403, detail="Opportunity not tracked by user/team")


# ------------------------------
# Company profile caching helper
# ------------------------------
import json
import logging
from typing import Any, Dict

# Simple in-memory cache (cleared on restart)
_company_profile_cache: Dict[str, Dict[str, Any]] = {}


async def get_company_profile_cached(conn, user_id: str, team_id: str | None = None) -> Dict[str, Any]:
    """
    Fetch user's company profile with simple caching.
    Cache is per-request lifetime (cleared on app restart).
    """
    cache_key = f"{user_id}:{team_id or ''}"
    if cache_key in _company_profile_cache:
        return _company_profile_cache[cache_key]

    try:
        res = await conn.exec_driver_sql(
            "SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1",
            {"uid": user_id},
        )
        row = res.first()
        if row and row[0]:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            profile = merge_company_profile_defaults(data)
            _company_profile_cache[cache_key] = profile
            return profile

        # Fallback: if user has no profile but belongs to a team, use the team's profile if available
        if team_id:
            team_res = await conn.exec_driver_sql(
                """
                SELECT cp.data
                FROM company_profiles cp
                JOIN users u ON u.id = cp.user_id
                WHERE u.team_id = :team_id
                ORDER BY cp.updated_at DESC NULLS LAST, cp.created_at DESC NULLS LAST
                LIMIT 1
                """,
                {"team_id": team_id},
            )
            trow = team_res.first()
            if trow and trow[0]:
                data = trow[0] if isinstance(trow[0], dict) else json.loads(trow[0])
                profile = merge_company_profile_defaults(data)
                _company_profile_cache[cache_key] = profile
                return profile
    except Exception as e:
        logging.error(f"Failed to load company profile for user {user_id}: {e}")

    default = merge_company_profile_defaults({})
    _company_profile_cache[cache_key] = default
    return default


def clear_company_profile_cache(user_id: str):
    """Remove a user's company profile from cache after update."""
    if not user_id:
        return
    keys_to_remove = [k for k in _company_profile_cache.keys() if k.startswith(f"{user_id}:") or k == user_id]
    for k in keys_to_remove:
        _company_profile_cache.pop(k, None)
