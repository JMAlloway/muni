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
from typing import Any, Dict

# Simple in-memory cache (cleared on restart)
_company_profile_cache: Dict[str, Dict[str, Any]] = {}


async def get_company_profile_cached(conn, user_id: str) -> Dict[str, Any]:
    """
    Fetch user's company profile with simple caching.
    Cache is per-request lifetime (cleared on app restart).
    """
    # Check cache
    if user_id in _company_profile_cache:
        return _company_profile_cache[user_id]

    try:
        res = await conn.exec_driver_sql(
            "SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1",
            {"uid": user_id},
        )
        row = res.first()
        if row and row[0]:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            profile = merge_company_profile_defaults(data)
            _company_profile_cache[user_id] = profile
            return profile
    except Exception:
        pass

    default = merge_company_profile_defaults({})
    _company_profile_cache[user_id] = default
    return default


def clear_company_profile_cache(user_id: str = None):
    """Clear cache for a specific user or all users."""
    if user_id:
        _company_profile_cache.pop(user_id, None)
    else:
        _company_profile_cache.clear()
