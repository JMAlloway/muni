from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.session import get_current_user_email
from app.core.db_core import engine

router = APIRouter(prefix="/api/tracked", tags=["tracked"])


async def _require_user(request: Request):
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT id, email FROM users WHERE email = :e LIMIT 1",
            {"e": email},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    m = row._mapping
    return {"id": m["id"], "email": m["email"]}


@router.get("/my")
async def my_tracked(user=Depends(_require_user)):
    """
    Return active tracked opportunities for current user (id, title, due_date).
    """
    q = """
        SELECT o.id, o.title, o.due_date, o.agency_name
        FROM user_bid_trackers t
        JOIN opportunities o ON o.id = t.opportunity_id
        WHERE t.user_id = :uid
          AND COALESCE(t.status, '') NOT LIKE '%archive%'
        ORDER BY o.due_date IS NULL, o.due_date ASC, o.title ASC
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(q, {"uid": user["id"]})
        rows = [dict(r._mapping) for r in res.fetchall()]
    return rows
