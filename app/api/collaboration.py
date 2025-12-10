from typing import Dict, Set, Any, List, Optional

import json
import datetime as dt
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.auth.session import SESSION_COOKIE_NAME, parse_session_token
from app.core.db_core import engine

router = APIRouter(tags=["collaboration"])


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[int, Set[WebSocket]] = {}
        self.presence: Dict[int, Set[str]] = {}

    async def connect(self, ws: WebSocket, response_id: int, user_email: str) -> None:
        await ws.accept()
        self.rooms.setdefault(response_id, set()).add(ws)
        self.presence.setdefault(response_id, set()).add(user_email)
        await self.broadcast(
            response_id,
            {"type": "presence", "users": list(self.presence.get(response_id, []))},
        )

    async def disconnect(self, ws: WebSocket, response_id: int, user_email: str) -> None:
        try:
            if response_id in self.rooms:
                self.rooms[response_id].discard(ws)
            if response_id in self.presence:
                self.presence[response_id].discard(user_email)
        finally:
            await self.broadcast(
                response_id,
                {"type": "presence", "users": list(self.presence.get(response_id, []))},
            )

    async def broadcast(self, response_id: int, message: Dict[str, Any]) -> None:
        conns = list(self.rooms.get(response_id, set()))
        for ws in conns:
            if ws.application_state != WebSocketState.CONNECTED:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                try:
                    await ws.close()
                except Exception:
                    pass
                self.rooms.get(response_id, set()).discard(ws)


manager = ConnectionManager()


async def _get_user_for_ws(ws: WebSocket) -> Dict[str, Any] | None:
    token = ws.cookies.get(SESSION_COOKIE_NAME)
    email = parse_session_token(token)
    if not email:
        return None
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT id, email, team_id FROM users WHERE email = :e LIMIT 1",
            {"e": email},
        )
        row = res.first()
    if not row:
        return None
    m = row._mapping
    return {"id": m["id"], "email": m["email"], "team_id": m.get("team_id")}


async def _user_can_access_response(user: Dict[str, Any], response_id: int) -> Dict[str, Any] | None:
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT id, user_id, team_id, opportunity_id
            FROM rfp_responses
            WHERE id = :id
            LIMIT 1
            """,
            {"id": response_id},
        )
        row = res.first()
    if not row:
        return None
    rec = row._mapping
    if rec["user_id"] == user["id"]:
        return rec
    if rec.get("team_id") and rec["team_id"] == user.get("team_id"):
        return rec
    return None


async def _load_review_comments(response_id: int) -> List[Dict[str, Any]]:
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT review_comments FROM rfp_responses WHERE id = :id LIMIT 1", {"id": response_id}
        )
        row = res.first()
    if not row:
        return []
    data = row[0]
    try:
        return json.loads(data) if isinstance(data, str) else (data or [])
    except Exception:
        return []


async def _load_comments(response_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return combined comments: review_comments (RFQ responses) + team bid notes for this opportunity.
    """
    response_id = response_record["id"]
    base_comments: List[Dict[str, Any]] = await _load_review_comments(response_id)

    team_comments: List[Dict[str, Any]] = []
    opp_id = response_record.get("opportunity_id")
    team_id = response_record.get("team_id")
    if opp_id and team_id:
        try:
            async with engine.begin() as conn:
                note_res = await conn.exec_driver_sql(
                    """
                    SELECT bn.body, bn.author_user_id, bn.created_at, u.email AS author_email
                    FROM bid_notes bn
                    LEFT JOIN users u ON u.id = bn.author_user_id
                    WHERE bn.team_id = :team AND bn.opportunity_id = :oid
                    ORDER BY bn.created_at ASC
                    LIMIT 100
                    """,
                    {"team": team_id, "oid": opp_id},
                )
                team_comments = [
                    {
                        "type": "comment",
                        "section_id": None,
                        "content": note._mapping["body"],
                        "user": note._mapping.get("author_email") or str(note._mapping.get("author_user_id") or ""),
                        "created_at": str(note._mapping.get("created_at") or ""),
                        "source": "team_thread",
                    }
                    for note in note_res.fetchall()
                ]
        except Exception:
            team_comments = []

    return team_comments + base_comments


async def _save_comment(response_record: Dict[str, Any], comment: Dict[str, Any], user: Dict[str, Any]) -> None:
    response_id = response_record["id"]
    existing = await _load_review_comments(response_id)
    existing.append(comment)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "UPDATE rfp_responses SET review_comments = :c, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"c": json.dumps(existing), "id": response_id},
        )

    # Also mirror into team bid notes for sidebar/thread if team/opportunity available
    opp_id = response_record.get("opportunity_id")
    team_id = response_record.get("team_id")
    if opp_id and team_id:
        body = comment.get("content") or ""
        section = comment.get("section_id")
        prefix = f"[Section {section}] " if section else ""
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    """
                    INSERT INTO bid_notes (id, team_id, opportunity_id, author_user_id, body, mentions, created_at)
                    VALUES (:id, :team, :oid, :author, :body, :mentions, :created_at)
                    """,
                    {
                        "id": str(uuid.uuid4()),
                        "team": team_id,
                        "oid": opp_id,
                        "author": user.get("id"),
                        "body": prefix + body,
                        "mentions": json.dumps([]),
                        "created_at": dt.datetime.utcnow(),
                    },
                )
        except Exception:
            pass


@router.websocket("/ws/response/{response_id}")
async def response_editor(websocket: WebSocket, response_id: int):
    user = await _get_user_for_ws(websocket)
    if not user:
        await websocket.close(code=4401)
        return
    response_record = await _user_can_access_response(user, response_id)
    if not response_record:
        await websocket.close(code=4403)
        return

    await manager.connect(websocket, response_id, user["email"])
    # Send initial comments/presence snapshot
    try:
        await websocket.send_json(
            {
                "type": "init",
                "comments": await _load_comments(response_record),
                "presence": list(manager.presence.get(response_id, [])),
            }
        )
    except Exception:
        pass
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            msg_type = data.get("type")
            if msg_type == "edit":
                payload = {
                    "type": "edit",
                    "section_id": data.get("section_id"),
                    "content": data.get("content"),
                    "user": user["email"],
                    "cursor_position": data.get("cursor"),
                }
                await manager.broadcast(response_id, payload)
            elif msg_type == "comment":
                payload = {
                    "type": "comment",
                    "section_id": data.get("section_id"),
                    "content": data.get("content"),
                    "user": user["email"],
                    "created_at": data.get("created_at"),
                }
                await _save_comment(response_record, payload, user)
                await manager.broadcast(response_id, payload)
            elif msg_type == "presence":
                await manager.broadcast(
                    response_id,
                    {"type": "presence", "users": list(manager.presence.get(response_id, []))},
                )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, response_id, user["email"])
