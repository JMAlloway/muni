import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db_core import engine
from app.auth.session import get_current_user_email

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _require_email(request: Request) -> str:
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return email


@router.get("/order", response_class=JSONResponse)
async def get_order(request: Request):
    email = await _require_email(request)
    # Ensure table and columns exist even if the table predates this feature
    async with engine.begin() as conn:
        await _ensure_user_prefs_schema(conn)
        res = await conn.exec_driver_sql(
            "SELECT dashboard_order FROM user_preferences WHERE user_email = :e",
            {"e": email},
        )
        row = res.first()
    if not row or row[0] is None:
        return {"order": []}
    # SQLite returns TEXT; ensure we give back a list
    try:
        val = row[0]
        if isinstance(val, str):
            val = json.loads(val)
        if not isinstance(val, list):
            val = []
    except Exception:
        val = []
    return {"order": val}


@router.post("/order", response_class=JSONResponse)
async def set_order(request: Request):
    email = await _require_email(request)
    try:
        payload = await request.json()
        order = payload.get("order", [])
        if not isinstance(order, list):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    async with engine.begin() as conn:
        await _ensure_user_prefs_schema(conn)
        # upsert
        await conn.exec_driver_sql(
            """
            INSERT INTO user_preferences (user_email, dashboard_order)
            VALUES (:e, :o)
            ON CONFLICT(user_email) DO UPDATE SET
                dashboard_order = excluded.dashboard_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            {"e": email, "o": json.dumps(order)},
        )
    return {"ok": True}


async def _ensure_user_prefs_schema(conn):
    # Create table if missing
    await conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_email TEXT PRIMARY KEY,
            agencies JSON,
            keywords JSON,
            frequency TEXT,
            dashboard_order JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Add missing columns on older dev DBs
    res = await conn.exec_driver_sql("PRAGMA table_info(user_preferences)")
    cols = [row[1] for row in res.fetchall()]
    if "dashboard_order" not in cols:
        try:
            await conn.exec_driver_sql("ALTER TABLE user_preferences ADD COLUMN dashboard_order JSON")
        except Exception:
            pass
    if "created_at" not in cols:
        try:
            await conn.exec_driver_sql("ALTER TABLE user_preferences ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass
    if "updated_at" not in cols:
        try:
            await conn.exec_driver_sql("ALTER TABLE user_preferences ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass
