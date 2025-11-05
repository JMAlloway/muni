from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from app.db_core import engine
from app.auth import get_current_user  # async, returns User

router = APIRouter(prefix="/tracker", tags=["tracker"])

@router.post("/{opportunity_id}/track")
async def track_opportunity(opportunity_id: int, user=Depends(get_current_user)):
    q_ins = text("""
        INSERT INTO user_bid_trackers (user_id, opportunity_id)
        VALUES (:uid, :oid)
        ON CONFLICT(user_id, opportunity_id) DO NOTHING
    """)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(q_ins, {"uid": user.id, "oid": opportunity_id})
    return {"ok": True}

@router.get("/{opportunity_id}")
async def get_tracker(opportunity_id: int, user=Depends(get_current_user)):
    q = text("""
        SELECT id, status, notes, created_at
        FROM user_bid_trackers
        WHERE user_id = :uid AND opportunity_id = :oid
        LIMIT 1
    """)
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(q, {"uid": user.id, "oid": opportunity_id})
        row = res.first()
    if not row:
        raise HTTPException(404, "Not tracked")
    return dict(row._mapping)

@router.patch("/{opportunity_id}")
async def update_tracker(opportunity_id: int, payload: dict, user=Depends(get_current_user)):
    fields = []
    params = {"uid": user.id, "oid": opportunity_id}
    if "status" in payload:
        fields.append("status = :status"); params["status"] = payload["status"]
    if "notes" in payload:
        fields.append("notes = :notes"); params["notes"] = payload["notes"]
    if not fields:
        return {"ok": True}
    q = text(f"""
        UPDATE user_bid_trackers
        SET {", ".join(fields)}
        WHERE user_id = :uid AND opportunity_id = :oid
    """)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(q, params)
    return {"ok": True}
