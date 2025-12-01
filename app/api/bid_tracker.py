from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.db_core import engine
from app.auth.session import get_current_user_email  # uses session cookie
from app.services import record_milestone

router = APIRouter(prefix="/tracker", tags=["tracker"])


# ============================================================
# Helper functions
# ============================================================

async def _require_user(request: Request):
    """
    Return {'id': int, 'email': str} based on session cookie.
    Raise 401 if not logged in or missing user.
    """
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT id, email FROM users WHERE email = :e LIMIT 1",
            {"e": email}
        )
        row = res.first()

    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")

    m = row._mapping
    return {"id": m["id"], "email": m["email"]}


async def _resolve_opportunity_id(key: str) -> int:
    """
    Accept either internal numeric id (e.g. '42')
    OR an alphanumeric external_id (e.g. '31fab7c4...').
    Return the internal integer id or raise 404.
    """
    async with engine.begin() as conn:
        # Numeric id path
        if key.isdigit():
            res = await conn.exec_driver_sql(
                "SELECT id FROM opportunities WHERE id = :k LIMIT 1",
                {"k": int(key)}
            )
            row = res.first()
            if row:
                return row[0]

        # External id path
        res = await conn.exec_driver_sql(
            """
            SELECT id
            FROM opportunities
            WHERE external_id = :k
               OR CAST(id AS TEXT) = :k
            LIMIT 1
            """,
            {"k": key}
        )
        row = res.first()
        if row:
            return row[0]

    raise HTTPException(status_code=404, detail="Opportunity not found")


# ============================================================
# Utility: active tracker count
# ============================================================

@router.get("/count", include_in_schema=False)
async def tracker_count(user=Depends(_require_user)):
    """
    Return count of active (non-archived) tracked opportunities for the current user.
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM user_bid_trackers
            WHERE user_id = :uid AND COALESCE(status, '') NOT LIKE '%archive%'
            """,
            {"uid": user["id"]},
        )
        count = res.scalar() or 0
    return {"count": count}


# ============================================================
# Routes
# ============================================================

@router.post("/{opportunity_key}/track")
async def track_opportunity(opportunity_key: str, user=Depends(_require_user)):
    """
    Create tracker row for user and opportunity (id or external_id).
    Safe to call repeatedly — ON CONFLICT DO NOTHING.
    """
    oid = await _resolve_opportunity_id(opportunity_key)

    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            INSERT INTO user_bid_trackers (user_id, opportunity_id)
            VALUES (:uid, :oid)
            ON CONFLICT(user_id, opportunity_id) DO NOTHING
            """,
            {"uid": user["id"], "oid": oid}
        )
        count_res = await conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM user_bid_trackers
            WHERE user_id = :uid AND COALESCE(status, '') NOT LIKE '%archive%'
            """,
            {"uid": user["id"]},
        )
        count = count_res.scalar() or 0

    first_time = await record_milestone(user["email"], "tracked_first", {"opportunity_id": oid})

    return {"ok": True, "first_time": first_time, "count": count}


@router.get("/{opportunity_key}")
async def get_tracker(opportunity_key: str, user=Depends(_require_user)):
    """
    Return tracker entry for this user/opportunity.
    If not tracked, return a benign payload instead of raising.
    Best-effort even if the opportunity row is missing.
    """
    async with engine.begin() as conn:
        # Try exact opportunity_id match first
        if opportunity_key.isdigit():
            res = await conn.exec_driver_sql(
                """
                SELECT id, status, notes, created_at
                FROM user_bid_trackers
                WHERE user_id = :uid AND opportunity_id = :oid
                LIMIT 1
                """,
                {"uid": user["id"], "oid": int(opportunity_key)},
            )
            row = res.first()
            if row:
                return dict(row._mapping)

        # Then try via external_id join
        res = await conn.exec_driver_sql(
            """
            SELECT t.id, t.status, t.notes, t.created_at
            FROM user_bid_trackers t
            JOIN opportunities o ON o.id = t.opportunity_id
            WHERE t.user_id = :uid AND (o.external_id = :key OR CAST(o.id AS TEXT) = :key)
            LIMIT 1
            """,
            {"uid": user["id"], "key": opportunity_key},
        )
        row = res.first()
        if row:
            return dict(row._mapping)

    # not tracked
    return {"id": None, "status": None, "notes": "", "created_at": None, "tracked": False}


@router.patch("/{opportunity_key}")
async def update_tracker(opportunity_key: str, payload: dict, user=Depends(_require_user)):
    """
    Upsert tracker row, then update status/notes.
    """
    oid = await _resolve_opportunity_id(opportunity_key)

    # Always ensure the row exists first (idempotent)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            INSERT INTO user_bid_trackers (user_id, opportunity_id)
            VALUES (:uid, :oid)
            ON CONFLICT(user_id, opportunity_id) DO NOTHING
            """,
            {"uid": user["id"], "oid": oid}
        )

    # Now apply updates
    fields = []
    params = {"uid": user["id"], "oid": oid}
    if "status" in payload:
        fields.append("status = :status")
        params["status"] = payload["status"]
    if "notes" in payload:
        fields.append("notes = :notes")
        params["notes"] = payload["notes"]

    if fields:
        sql = f"""
            UPDATE user_bid_trackers
            SET {", ".join(fields)}
            WHERE user_id = :uid AND opportunity_id = :oid
        """
        async with engine.begin() as conn:
            await conn.exec_driver_sql(sql, params)

    return {"ok": True}

@router.get("/mine")
async def my_tracked(user=Depends(_require_user)):
    """
    Return list of all tracked opportunities for current user.
    Used for dashboard view.
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT
              t.opportunity_id,
              o.external_id,
              o.title,
              o.agency_name,
              COALESCE(o.ai_category, o.category) AS category,
              o.due_date
            FROM user_bid_trackers t
            JOIN opportunities o ON o.id = t.opportunity_id
            WHERE t.user_id = :uid
            ORDER BY (o.due_date IS NULL) ASC, o.due_date ASC, t.created_at DESC
            """,
            {"uid": user["id"]}
        )
        rows = res.fetchall()

    return [dict(r._mapping) for r in rows]


@router.delete("/{opportunity_key}")
async def delete_tracker(opportunity_key: str, user=Depends(_require_user)):
    """
    Delete the tracker row for this user/opportunity.
    Safe to call; no-op if it doesn't exist.
    Best-effort even if the opportunity row is missing.
    """
    oid = None
    try:
        oid = await _resolve_opportunity_id(opportunity_key)
    except HTTPException:
        if opportunity_key.isdigit():
            oid = int(opportunity_key)

    async with engine.begin() as conn:
        if oid is not None:
            await conn.exec_driver_sql(
                """
                DELETE FROM user_bid_trackers
                WHERE user_id = :uid AND opportunity_id = :oid
                """,
                {"uid": user["id"], "oid": oid},
            )
        else:
            # fallback: try deleting by external_id mapping
            await conn.exec_driver_sql(
                """
                DELETE FROM user_bid_trackers
                WHERE user_id = :uid
                  AND opportunity_id IN (
                    SELECT id FROM opportunities WHERE external_id = :ext LIMIT 1
                  )
                """,
                {"uid": user["id"], "ext": opportunity_key},
            )
        count_res = await conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM user_bid_trackers
            WHERE user_id = :uid AND COALESCE(status, '') NOT LIKE '%archive%'
            """,
            {"uid": user["id"]},
        )
        count = count_res.scalar() or 0

    return {"ok": True, "count": count}


@router.get("/count")
async def tracker_count(user=Depends(_require_user)):
    """
    Return count of active (non-archived) tracked opportunities for the current user.
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT COUNT(*) FROM user_bid_trackers
            WHERE user_id = :uid AND COALESCE(status, '') NOT LIKE '%archive%'
            """,
            {"uid": user["id"]},
        )
        count = res.scalar() or 0
    return {"count": count}
