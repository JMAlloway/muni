from typing import Any, Dict, List, Optional
import datetime as dt
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth.session import get_current_user_email
from app.core.db import AsyncSessionLocal

router = APIRouter(tags=["notifications"])


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    recipient_user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata TEXT,
    read_at DATETIME,
    actioned_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


async def _ensure_table(session):
    await session.execute(text(CREATE_TABLE_SQL))


def _row_to_dict(row) -> Dict[str, Any]:
    m = row._mapping
    def _iso(val):
        if val is None:
            return None
        try:
            return val.isoformat()
        except AttributeError:
            try:
                # If already a string, normalize best-effort.
                return str(val)
            except Exception:
                return None

    return {
        "id": m["id"],
        "type": m["type"],
        "title": m["title"],
        "body": m["body"],
        "metadata": json.loads(m["metadata"]) if m["metadata"] else {},
        "read_at": _iso(m["read_at"]),
        "actioned_at": _iso(m["actioned_at"]),
        "created_at": _iso(m["created_at"]),
    }


async def create_notification(
    session,
    *,
    recipient_user_id: str,
    notif_type: str,
    title: str,
    body: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    await _ensure_table(session)
    notif_id = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO notifications (id, recipient_user_id, type, title, body, metadata, created_at)
            VALUES (:id, :uid, :type, :title, :body, :metadata, :created_at)
            """
        ),
        {
            "id": notif_id,
            "uid": recipient_user_id,
            "type": notif_type,
            "title": title,
            "body": body,
            "metadata": json.dumps(metadata or {}),
            "created_at": dt.datetime.utcnow(),
        },
    )
    return notif_id


async def _get_user(session, email: str):
    res = await session.execute(
        text("SELECT id, email FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
        {"email": email},
    )
    return res.fetchone()


@router.get("/api/notifications", response_class=JSONResponse)
async def list_notifications(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        await _ensure_table(session)
        user_row = await _get_user(session, user_email)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = user_row[0]

        res = await session.execute(
            text(
                """
                SELECT id, type, title, body, metadata, read_at, actioned_at, created_at
                FROM notifications
                WHERE recipient_user_id = :uid
                ORDER BY datetime(created_at) DESC
                LIMIT 50
                """
            ),
            {"uid": user_id},
        )
        rows = res.fetchall()

        unread_res = await session.execute(
            text(
                """
                SELECT COUNT(*) FROM notifications
                WHERE recipient_user_id = :uid AND read_at IS NULL
                """
            ),
            {"uid": user_id},
        )
        unread_count = unread_res.scalar() or 0

    return {"notifications": [_row_to_dict(r) for r in rows], "unread_count": unread_count}


@router.post("/api/notifications/{notification_id}/read", response_class=JSONResponse)
async def mark_notification_read(request: Request, notification_id: str):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncSessionLocal() as session:
        await _ensure_table(session)
        user_row = await _get_user(session, user_email)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = user_row[0]
        await session.execute(
            text(
                """
                UPDATE notifications
                SET read_at = COALESCE(read_at, :ts)
                WHERE id = :id AND recipient_user_id = :uid
                """
            ),
            {"id": notification_id, "uid": user_id, "ts": dt.datetime.utcnow()},
        )
        await session.commit()
    return {"ok": True}


async def _accept_team_invite(session, user_email: str, team_id: Optional[str]):
    res = await session.execute(
        text("SELECT id FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
        {"email": user_email},
    )
    user_row = res.fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    user_id = user_row[0]

    if team_id:
        invite_res = await session.execute(
            text(
                """
                SELECT team_id FROM team_members
                WHERE invited_email = :email AND team_id = :team
                ORDER BY invited_at DESC
                LIMIT 1
                """
            ),
            {"email": user_email, "team": team_id},
        )
    else:
        invite_res = await session.execute(
            text(
                """
                SELECT team_id FROM team_members
                WHERE invited_email = :email
                ORDER BY invited_at DESC
                LIMIT 1
                """
            ),
            {"email": user_email},
        )
    invite_row = invite_res.fetchone()
    if not invite_row:
        raise HTTPException(status_code=404, detail="No pending invite")
    target_team_id = invite_row[0]

    await session.execute(
        text(
            """
            UPDATE team_members
            SET user_id = :uid, accepted_at = CURRENT_TIMESTAMP
            WHERE team_id = :team AND invited_email = :email
            """
        ),
        {"team": target_team_id, "email": user_email, "uid": user_id},
    )
    await session.execute(
        text("UPDATE users SET team_id = :team WHERE id = :uid"),
        {"team": target_team_id, "uid": user_id},
    )


async def _decline_team_invite(session, user_email: str, team_id: Optional[str]):
    if team_id:
        await session.execute(
            text(
                """
                DELETE FROM team_members
                WHERE invited_email = :email AND team_id = :team AND accepted_at IS NULL
                """
            ),
            {"email": user_email, "team": team_id},
        )
    else:
        await session.execute(
            text(
                """
                DELETE FROM team_members
                WHERE invited_email = :email AND accepted_at IS NULL
                """
            ),
            {"email": user_email},
        )


@router.post("/api/notifications/{notification_id}/action", response_class=JSONResponse)
async def act_on_notification(request: Request, notification_id: str, payload: Dict[str, Any]):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    action = (payload.get("action") or "").strip().lower()
    if action not in {"accept", "decline"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    async with AsyncSessionLocal() as session:
        await _ensure_table(session)
        user_row = await _get_user(session, user_email)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = user_row[0]

        res = await session.execute(
            text(
                """
                SELECT id, type, metadata, actioned_at FROM notifications
                WHERE id = :id AND recipient_user_id = :uid
                LIMIT 1
                """
            ),
            {"id": notification_id, "uid": user_id},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        if row._mapping.get("actioned_at"):
            return {"ok": True, "already_actioned": True}

        metadata = {}
        raw_meta = row._mapping.get("metadata")
        try:
            metadata = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            metadata = {}
        notif_type = row._mapping.get("type")
        team_id = metadata.get("team_id")

        if notif_type == "team_invite":
            if action == "accept":
                await _accept_team_invite(session, user_email, team_id)
            elif action == "decline":
                await _decline_team_invite(session, user_email, team_id)

        await session.execute(
            text(
                """
                UPDATE notifications
                SET actioned_at = :ts, read_at = COALESCE(read_at, :ts)
                WHERE id = :id AND recipient_user_id = :uid
                """
            ),
            {"ts": dt.datetime.utcnow(), "id": notification_id, "uid": user_id},
        )
        await session.commit()

    return {"ok": True}
