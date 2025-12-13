import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth_helpers import ensure_user_can_access_opportunity, require_user_with_team
from app.core.db_core import engine

_RECENT_LIMIT_MAX = 100
_MAX_STATE_BYTES = 1_000_000  # 1 MB safeguard for stored session state
_MAX_SECTIONS = 200
_MAX_LATEST_SECTIONS = 200
_MAX_NAME_LENGTH = 255
_COMPLETED_WORD_THRESHOLD = 20

router = APIRouter(prefix="/api/ai-sessions", tags=["ai-sessions"])


def _load_state_json(raw_state: Any) -> Dict[str, Any]:
    if not raw_state:
        return {}
    try:
        parsed = json.loads(raw_state)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Corrupted session state.")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session state format is invalid.")
    return parsed


def _validate_state_payload(raw_state: Any) -> Dict[str, Any]:
    if raw_state is None:
        return {}
    if not isinstance(raw_state, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="state must be an object.")
    return raw_state


def _validate_name(name: Any) -> str | None:
    if name is None:
        return None
    if not isinstance(name, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name must be a string.")
    cleaned = name.strip()
    if len(cleaned) > _MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"name must be {_MAX_NAME_LENGTH} characters or fewer.",
        )
    return cleaned or None


def _validate_opportunity_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int)):
        return str(value)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="opportunity_id must be a string.")


def _validated_list(state: Dict[str, Any], key: str, max_len: int) -> List[Any]:
    raw = state.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"state.{key} must be a list.",
        )
    if len(raw) > max_len:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"state.{key} exceeds maximum length of {max_len}.",
        )
    return raw


def _count_completed_sections(latest_sections: List[Any]) -> int:
    completed = 0
    for section in latest_sections:
        if not isinstance(section, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="latestSections entries must be objects."
            )
        answer = section.get("answer")
        if isinstance(answer, str) and len(answer.split()) > _COMPLETED_WORD_THRESHOLD:
            completed += 1
    return completed


def _serialize_state(state: Dict[str, Any]) -> str:
    state_json = json.dumps(state, ensure_ascii=False)
    if len(state_json.encode("utf-8")) > _MAX_STATE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"state is too large; limit {_MAX_STATE_BYTES} bytes.",
        )
    return state_json


@router.get("/recent")
async def list_recent_sessions(
    limit: int = Query(10, ge=1, le=_RECENT_LIMIT_MAX), user=Depends(require_user_with_team)
) -> List[Dict[str, Any]]:
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
        state = _load_state_json(row.get("state_json"))
        sections = state.get("sections") or []
        if sections and not isinstance(sections, list):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session state format is invalid."
            )
        row["sections_count"] = len(sections) if isinstance(sections, list) else 0
        row["has_drafts"] = bool(state.get("coverDraft") or state.get("soqDraft"))
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        await conn.exec_driver_sql(
            "UPDATE ai_studio_sessions SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": session_id},
        )

    data = dict(row._mapping)
    data["state"] = _load_state_json(data.get("state_json"))
    data.pop("state_json", None)

    return data


@router.post("/save")
async def save_session(payload: Dict[str, Any], user=Depends(require_user_with_team)) -> Dict[str, Any]:
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id.isdigit():
        session_id = int(session_id)
    if session_id is not None and not isinstance(session_id, int):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_id must be an integer.")

    opportunity_id = _validate_opportunity_id(payload.get("opportunity_id"))
    if opportunity_id:
        await ensure_user_can_access_opportunity(user, opportunity_id)

    state = _validate_state_payload(payload.get("state"))
    name = _validate_name(payload.get("name"))

    sections = _validated_list(state, "sections", _MAX_SECTIONS)
    latest_sections = _validated_list(state, "latestSections", _MAX_LATEST_SECTIONS)
    sections_total = len(sections)
    sections_completed = _count_completed_sections(latest_sections)
    has_cover = bool(state.get("coverDraft"))
    has_soq = bool(state.get("soqDraft"))

    state_json = _serialize_state(state)

    async with engine.begin() as conn:
        if session_id:
            result = await conn.exec_driver_sql(
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
            if result.rowcount > 0:
                return {"session_id": session_id, "status": "updated"}
            # If the session was not found (e.g., deleted in another tab), fall through to create a new one
        res = await conn.exec_driver_sql(
            """
            INSERT INTO ai_studio_sessions
                (user_id, team_id, opportunity_id, name, state_json,
                 sections_total, sections_completed, has_cover_letter, has_soq)
            VALUES (:uid, :team_id, :oid, :name, :state, :total, :completed, :cover, :soq)
            RETURNING id
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
        new_id = res.scalar_one()
        return {"session_id": new_id, "status": "created"}


@router.delete("/{session_id}")
async def delete_session(session_id: int, user=Depends(require_user_with_team)) -> Dict[str, str]:
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            DELETE FROM ai_studio_sessions
            WHERE id = :id 
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": session_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or access denied")
    return {"status": "deleted"}
