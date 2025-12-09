import datetime
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.response_validator import run_basic_checks
from app.services.rfp_generator import generate_section_answer
from app.services.company_profile_template import merge_company_profile_defaults
from app.storage import read_storage_bytes

router = APIRouter(prefix="/api/rfp-responses", tags=["rfp-responses"])


async def _require_user(request: Request):
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


async def _get_company_profile(user_id: Any) -> Dict[str, Any]:
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                "SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1",
                {"uid": user_id},
            )
            row = res.first()
            if row and row[0]:
                data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                return merge_company_profile_defaults(data)
    except Exception:
        pass
    return merge_company_profile_defaults({})


async def _get_win_themes(user: dict, theme_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"uid": user["id"], "team_id": user.get("team_id")}
    cond = "(user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))"
    select = """
        SELECT id, title, description, category, supporting_docs, metrics, times_used, last_used_at
        FROM win_themes
        WHERE {cond}
    """
    if theme_ids:
        placeholders = ", ".join([f":id{i}" for i in range(len(theme_ids))])
        select += f" AND id IN ({placeholders})"
        for idx, val in enumerate(theme_ids):
            params[f"id{idx}"] = val
    select = select.format(cond=cond)
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(select, params)
            rows = [dict(r._mapping) for r in res.fetchall()]
        for row in rows:
            row["supporting_docs"] = json.loads(row["supporting_docs"]) if row.get("supporting_docs") else []
            row["metrics"] = json.loads(row["metrics"]) if row.get("metrics") else {}
        return rows
    except Exception:
        return []


async def _get_knowledge_docs(user: dict, doc_ids: Optional[List[int]] = None, limit: int = 15) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"uid": user["id"], "team_id": user.get("team_id"), "limit": limit}
    cond = "(user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))"
    query = f"""
        SELECT id, filename, doc_type, extracted_text, tags, updated_at
        FROM knowledge_documents
        WHERE {cond}
    """
    if doc_ids:
        placeholders = ", ".join([f":id{i}" for i in range(len(doc_ids))])
        query += f" AND id IN ({placeholders})"
        for idx, val in enumerate(doc_ids):
            params[f"id{idx}"] = val
    query += " AND COALESCE(extraction_status, '') IN ('success', 'completed')"
    query += " ORDER BY updated_at DESC"
    if not doc_ids:
        query += " LIMIT :limit"
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(query, params)
            rows = [dict(r._mapping) for r in res.fetchall()]
        for row in rows:
            row["tags"] = json.loads(row["tags"]) if row.get("tags") else []
        return rows
    except Exception:
        return []


async def _get_instruction_docs(user: dict, upload_ids: Optional[List[int]] = None, limit: int = 5) -> List[Dict[str, Any]]:
    if not upload_ids:
        return []
    params: Dict[str, Any] = {"uid": user["id"]}
    placeholders = ", ".join([f":id{i}" for i in range(len(upload_ids))])
    for idx, val in enumerate(upload_ids):
        params[f"id{idx}"] = val
    query = f"""
        SELECT id, filename, mime, storage_key, size
        FROM user_uploads
        WHERE user_id = :uid
          AND id IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT :limit
    """
    params["limit"] = limit or len(upload_ids)
    docs: List[Dict[str, Any]] = []
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(query, params)
            rows = [dict(r._mapping) for r in res.fetchall()]
    except Exception:
        rows = []

    processor = DocumentProcessor()
    for row in rows:
        try:
            data = read_storage_bytes(row["storage_key"])
            extraction = processor.extract_text(data, row.get("mime"), row.get("filename"))
            text = extraction.get("text") or ""
            docs.append(
                {
                    "id": row.get("id"),
                    "filename": row.get("filename"),
                    "extracted_text": text,
                    "mime": row.get("mime"),
                    "size": row.get("size"),
                }
            )
        except Exception:
            continue
    return docs


def _serialize_json(val: Any) -> str:
    try:
        return json.dumps(val)
    except Exception:
        return json.dumps([])


@router.post("/generate")
async def generate_rfp_response(payload: dict, user=Depends(_require_user)):
    opportunity_id = payload.get("opportunity_id")
    sections = payload.get("sections") or []
    if not opportunity_id:
        raise HTTPException(status_code=400, detail="opportunity_id is required")
    if not sections:
        raise HTTPException(status_code=400, detail="sections are required")

    win_theme_ids = payload.get("win_theme_ids") or []
    knowledge_doc_ids = payload.get("knowledge_doc_ids") or []
    custom_instructions = payload.get("custom_instructions") or ""
    instruction_upload_ids = payload.get("instruction_upload_ids") or []

    company_profile = await _get_company_profile(user["id"])
    win_themes = await _get_win_themes(user, win_theme_ids)
    knowledge_docs = await _get_knowledge_docs(user, knowledge_doc_ids)
    instruction_docs = await _get_instruction_docs(user, instruction_upload_ids)

    results = []
    issues = []
    for section in sections:
        generated = generate_section_answer(
            section,
            {
                "company_profile": company_profile,
                "win_themes": win_themes,
                "knowledge_docs": knowledge_docs,
                "custom_instructions": custom_instructions,
                "instruction_docs": instruction_docs,
            },
        )
        compliance = run_basic_checks(generated["answer"], section)
        issues.extend(compliance.get("issues") or [])
        results.append(
            {
                "id": section.get("id"),
                "question": section.get("question"),
                "max_words": section.get("max_words"),
                "required": section.get("required"),
                "answer": generated["answer"],
                "sources": generated["sources"],
                "win_themes_used": generated["win_themes_used"],
                "confidence": generated["confidence"],
                "word_count": generated["word_count"],
                "compliance": compliance,
            }
        )

    avg_score = 0.0
    scored = [r["compliance"]["score"] for r in results if r.get("compliance")]
    if scored:
        avg_score = round(sum(scored) / len(scored), 2)

    now = datetime.datetime.utcnow().isoformat()
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            INSERT INTO rfp_responses (
                user_id, team_id, opportunity_id, status, version,
                selected_win_themes, selected_knowledge_docs, custom_instructions,
                sections, compliance_score, compliance_issues,
                generated_at, created_at, updated_at
            )
            VALUES (
                :uid, :team_id, :opportunity_id, 'draft', 1,
                :win_themes, :knowledge_docs, :custom_instructions,
                :sections, :compliance_score, :compliance_issues,
                :generated_at, :created_at, :updated_at
            )
            """,
            {
                "uid": user["id"],
                "team_id": user.get("team_id"),
                "opportunity_id": opportunity_id,
                "win_themes": _serialize_json(win_theme_ids),
                "knowledge_docs": _serialize_json(knowledge_doc_ids),
                "custom_instructions": custom_instructions,
                "sections": json.dumps(results),
                "compliance_score": avg_score,
                "compliance_issues": json.dumps(issues),
                "generated_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = await conn.exec_driver_sql("SELECT last_insert_rowid() AS id")
        response_id = row.first()[0]

    return {
        "response_id": response_id,
        "status": "draft",
        "compliance_score": avg_score,
        "issues": issues,
        "sections": results,
        "generated_at": now,
    }


@router.get("/{response_id}")
async def get_rfp_response(response_id: int, user=Depends(_require_user)):
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT id, user_id, team_id, opportunity_id, status, version,
                   selected_win_themes, selected_knowledge_docs, custom_instructions,
                   sections, compliance_score, compliance_issues,
                   generated_at, submitted_at, created_at, updated_at
            FROM rfp_responses
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            LIMIT 1
            """,
            {"id": response_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = dict(row._mapping)
    data["selected_win_themes"] = json.loads(data["selected_win_themes"]) if data.get("selected_win_themes") else []
    data["selected_knowledge_docs"] = json.loads(data["selected_knowledge_docs"]) if data.get("selected_knowledge_docs") else []
    data["sections"] = json.loads(data["sections"]) if data.get("sections") else []
    data["compliance_issues"] = json.loads(data["compliance_issues"]) if data.get("compliance_issues") else []
    return data


@router.patch("/{response_id}/sections/{section_id}")
async def update_section(response_id: int, section_id: str, payload: dict, user=Depends(_require_user)):
    new_answer = (payload or {}).get("answer")
    if new_answer is None:
        raise HTTPException(status_code=400, detail="answer is required")

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT sections
            FROM rfp_responses
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": response_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        sections = json.loads(row[0]) if row[0] else []

        updated = False
        for s in sections:
            if str(s.get("id")) == str(section_id):
                s["answer"] = new_answer
                compliance = run_basic_checks(
                    new_answer,
                    {"max_words": s.get("max_words") or s.get("word_limit"), "required": s.get("required")},
                )
                s["compliance"] = compliance
                updated = True
                break

        if not updated:
            raise HTTPException(status_code=404, detail="Section not found")

        await conn.exec_driver_sql(
            """
            UPDATE rfp_responses
            SET sections = :sections,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {
                "sections": json.dumps(sections),
                "id": response_id,
                "uid": user["id"],
                "team_id": user.get("team_id"),
            },
        )

    return {"ok": True, "sections": sections}
