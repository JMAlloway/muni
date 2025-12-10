import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_helpers import require_user_with_team
from app.core.db_core import engine

router = APIRouter(prefix="/api/ai-sessions", tags=["ai-sessions"])


@router.get("/recent")
async def list_recent_sessions(limit: int = 10, user=Depends(require_user_with_team)) -> List[Dict[str, Any]]:
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT 
                s.id, s.opportunity_id, s.name, s.state_json,
                s.sections_total, s.sections_completed,
                s.has_cover_letter, s.has_soq,
                s.created_at, s.updated_at, s.last_accessed_at,
                o.title as opportunity_title, o.agency_name
            FROM ai_studio_sessions s
            LEFT JOIN opportunities o ON o.id = s.opportunity_id
            WHERE s.user_id = :uid 
               OR (s.team_id = :team_id AND :team_id IS NOT NULL)
            ORDER BY s.last_accessed_at DESC
            LIMIT :limit
            """,
            {"uid": user["id"], "team_id": user.get("team_id"), "limit": limit},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    for row in rows:
        try:
            state = json.loads(row.get("state_json") or "{}")
            row["sections_count"] = len(state.get("sections", []))
            row["has_drafts"] = bool(state.get("coverDraft") or state.get("soqDraft"))
        except Exception:
            row["sections_count"] = 0
            row["has_drafts"] = False
        row.pop("state_json", None)
    return rows


@router.get("/{session_id}")
async def get_session(session_id: int, user=Depends(require_user_with_team)) -> Dict[str, Any]:
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT id, opportunity_id, name, state_json, 
                   sections_total, sections_completed,
                   created_at, updated_at
            FROM ai_studio_sessions
            WHERE id = :id 
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": session_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        row = res.first()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    data = dict(row._mapping)
    try:
        data["state"] = json.loads(data.get("state_json") or "{}")
    except Exception:
        data["state"] = {}
    data.pop("state_json", None)

    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "UPDATE ai_studio_sessions SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": session_id},
        )

    return data


@router.post("/save")
async def save_session(payload: Dict[str, Any], user=Depends(require_user_with_team)) -> Dict[str, Any]:
    session_id = payload.get("session_id")
    opportunity_id = payload.get("opportunity_id")
    state = payload.get("state", {}) or {}
    name = payload.get("name")

    sections = state.get("sections", []) or []
    latest_sections = state.get("latestSections", []) or []
    sections_total = len(sections)
    sections_completed = sum(1 for s in latest_sections if s.get("answer") and len((s.get("answer") or "").split()) > 20)
    has_cover = bool(state.get("coverDraft"))
    has_soq = bool(state.get("soqDraft"))

    state_json = json.dumps(state)

    async with engine.begin() as conn:
        if session_id:
            await conn.exec_driver_sql(
                """
                UPDATE ai_studio_sessions 
                SET state_json = :state,
                    name = COALESCE(:name, name),
                    sections_total = :total,
                    sections_completed = :completed,
                    has_cover_letter = :cover,
                    has_soq = :soq,
                    updated_at = CURRENT_TIMESTAMP,
                    last_accessed_at = CURRENT_TIMESTAMP
                WHERE id = :id 
                  AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
                """,
                {
                    "id": session_id,
                    "state": state_json,
                    "name": name,
                    "total": sections_total,
                    "completed": sections_completed,
                    "cover": has_cover,
                    "soq": has_soq,
                    "uid": user["id"],
                    "team_id": user.get("team_id"),
                },
            )
            return {"session_id": session_id, "status": "updated"}
        else:
            await conn.exec_driver_sql(
                """
                INSERT INTO ai_studio_sessions 
                    (user_id, team_id, opportunity_id, name, state_json,
                     sections_total, sections_completed, has_cover_letter, has_soq)
                VALUES (:uid, :team_id, :oid, :name, :state, :total, :completed, :cover, :soq)
                """,
                {
                    "uid": user["id"],
                    "team_id": user.get("team_id"),
                    "oid": opportunity_id,
                    "name": name,
                    "state": state_json,
                    "total": sections_total,
                    "completed": sections_completed,
                    "cover": has_cover,
                    "soq": has_soq,
                },
            )
            row = await conn.exec_driver_sql("SELECT last_insert_rowid()")
            new_id = row.scalar()
            return {"session_id": new_id, "status": "created"}


@router.delete("/{session_id}")
async def delete_session(session_id: int, user=Depends(require_user_with_team)) -> Dict[str, str]:
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            DELETE FROM ai_studio_sessions
            WHERE id = :id 
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": session_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
    return {"status": "deleted"}
