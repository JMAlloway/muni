import asyncio
import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.api.uploads import ALLOWED_EXT, ALLOWED_MIME, MAX_BYTES, sanitize_filename
from app.storage import (
    BUCKET,
    LOCAL_DIR,
    USE_S3,
    _s3,
    create_presigned_get,
    read_storage_bytes,
    store_knowledge_bytes,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-base"])
ASYNC_THRESHOLD_BYTES = 5 * 1024 * 1024  # 5MB: run extraction async

DOC_TYPES = {
    "capability_statement",
    "past_performance",
    "technical_approach",
    "company_info",
    "certifications",
    "case_study",
    "other",
}


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


def _parse_tags(raw: str | list | None) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    # Fallback: comma-separated string
    return [t.strip() for t in str(raw).split(",") if t.strip()]


async def _get_doc(doc_id: int, user: dict, include_text: bool = False) -> dict:
    fields = "id, user_id, team_id, filename, mime, size, storage_key, doc_type, tags, extraction_status, extraction_error, created_at, updated_at"
    if include_text:
        fields += ", extracted_text"
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            f"""
            SELECT {fields}
            FROM knowledge_documents
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            LIMIT 1
            """,
            {"id": doc_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    record = dict(row._mapping)
    record["tags"] = json.loads(record["tags"]) if record.get("tags") else []
    return record


async def _run_async_extraction(doc_id: int, storage_key: str, mime: str, filename: str, user: dict) -> None:
    """Background extraction for large files; best-effort."""
    try:
        data = read_storage_bytes(storage_key)
        processor = DocumentProcessor()
        extraction = processor.extract_text(data, mime, filename)
        status_flag = extraction.get("status") or "pending"
        if status_flag == "success":
            status_flag = "completed"
        extracted_text = extraction.get("text") if status_flag == "completed" else ""
        extraction_error = extraction.get("error") if status_flag != "completed" else None
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                UPDATE knowledge_documents
                SET extracted_text = :extracted_text,
                    extraction_status = :extraction_status,
                    extraction_error = :extraction_error,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                  AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
                """,
                {
                    "extracted_text": extracted_text,
                    "extraction_status": status_flag,
                    "extraction_error": extraction_error,
                    "id": doc_id,
                    "uid": user["id"],
                    "team_id": user.get("team_id"),
                },
            )
    except Exception:
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    """
                    UPDATE knowledge_documents
                    SET extraction_status = 'failed',
                        extraction_error = 'Async extraction failed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                      AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
                    """,
                    {"id": doc_id, "uid": user["id"], "team_id": user.get("team_id")},
                )
        except Exception:
            return


@router.post("/upload")
async def upload_knowledge_documents(
    doc_type: str = Form("other"),
    tags: str = Form("[]"),
    files: List[UploadFile] = File(...),
    user=Depends(_require_user),
):
    if doc_type not in DOC_TYPES:
        doc_type = "other"
    tag_list = _parse_tags(tags)
    processor = DocumentProcessor()
    saved = []

    async with engine.begin() as conn:
        for up in files:
            safe_name = sanitize_filename(up.filename)
            mime = (up.content_type or "").lower().strip()
            if mime and mime not in ALLOWED_MIME:
                ext = os.path.splitext(safe_name)[1].lower().lstrip(".")
                if ext not in ALLOWED_EXT:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported file type: {mime or ext}",
                    )
            data = await up.read()
            if not data:
                continue
            if len(data) > MAX_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large (>{MAX_BYTES//(1024*1024)} MB)",
                )

            storage_key, size, mime = store_knowledge_bytes(
                str(user["id"]), user.get("team_id"), data, safe_name, mime
            )
            extraction = None
            status_flag = "pending"
            extracted_text = ""
            extraction_error = None

            if size > ASYNC_THRESHOLD_BYTES:
                status_flag = "processing"
            else:
                extraction = processor.extract_text(data, mime, safe_name)
                status_flag = extraction.get("status") or "pending"
                if status_flag == "success":
                    status_flag = "completed"
                extracted_text = extraction.get("text") if status_flag == "completed" else ""
                extraction_error = extraction.get("error") if status_flag != "completed" else None

            await conn.exec_driver_sql(
                """
                INSERT INTO knowledge_documents (
                    user_id, team_id, filename, mime, size, storage_key,
                    doc_type, tags, extracted_text, extraction_status, extraction_error
                )
                VALUES (
                    :uid, :team_id, :filename, :mime, :size, :storage_key,
                    :doc_type, :tags, :extracted_text, :extraction_status, :extraction_error
                )
                """,
                {
                    "uid": user["id"],
                    "team_id": user.get("team_id"),
                    "filename": safe_name,
                    "mime": mime,
                    "size": size,
                    "storage_key": storage_key,
                    "doc_type": doc_type,
                    "tags": json.dumps(tag_list),
                    "extracted_text": extracted_text,
                    "extraction_status": status_flag,
                    "extraction_error": extraction_error,
                },
            )
            row = await conn.exec_driver_sql("SELECT last_insert_rowid() AS id")
            rec_id = row.first()[0]

            # kick off async extraction if large
            if status_flag == "processing":
                try:
                    asyncio.create_task(_run_async_extraction(rec_id, storage_key, mime, safe_name, user))
                except Exception:
                    pass

            saved.append(
                {
                    "id": rec_id,
                    "filename": safe_name,
                    "size": size,
                    "mime": mime,
                    "doc_type": doc_type,
                    "tags": tag_list,
                    "download_url": create_presigned_get(storage_key),
                    "extraction_status": status_flag,
                    "extraction_metadata": (extraction or {}).get("metadata") if extraction else {},
                    "extraction_error": extraction_error,
                }
            )

    return {"ok": True, "files": saved}


@router.get("/list")
async def list_knowledge_documents(
    doc_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user=Depends(_require_user),
):
    conds = ["(user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))"]
    params = {"uid": user["id"], "team_id": user.get("team_id")}
    if doc_type:
        conds.append("doc_type = :doc_type")
        params["doc_type"] = doc_type
    if search:
        params["q"] = f"%{search.lower()}%"
        conds.append("(LOWER(filename) LIKE :q OR LOWER(extracted_text) LIKE :q)")
    where_clause = " AND ".join(conds)
    query = f"""
        SELECT id, user_id, team_id, filename, mime, size, storage_key,
               doc_type, tags, extraction_status, extraction_error,
               has_embeddings, created_at, updated_at
        FROM knowledge_documents
        WHERE {where_clause}
        ORDER BY updated_at DESC
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(query, params)
        rows = [dict(r._mapping) for r in res.fetchall()]

    for r in rows:
        r["tags"] = json.loads(r["tags"]) if r.get("tags") else []
        r["download_url"] = create_presigned_get(r["storage_key"])
    return rows


@router.delete("/{doc_id}")
async def delete_knowledge_document(doc_id: int, user=Depends(_require_user)):
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT storage_key FROM knowledge_documents
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": doc_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        storage_key = row._mapping["storage_key"]
        await conn.exec_driver_sql(
            """
            DELETE FROM knowledge_documents
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": doc_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        remain_res = await conn.exec_driver_sql(
            "SELECT COUNT(1) AS c FROM knowledge_documents WHERE storage_key = :k",
            {"k": storage_key},
        )
        remaining = remain_res.first()[0]

    if remaining == 0 and storage_key:
        try:
            if USE_S3:
                _s3.delete_object(Bucket=BUCKET, Key=storage_key)
            else:
                base = os.path.abspath(LOCAL_DIR)
                abspath = os.path.abspath(storage_key)
                if not abspath.startswith(base):
                    abspath = os.path.abspath(os.path.join(base, storage_key))
                if os.path.exists(abspath):
                    os.remove(abspath)
        except Exception:
            pass

    return {"ok": True}


@router.patch("/{doc_id}")
async def update_knowledge_document(doc_id: int, payload: dict, user=Depends(_require_user)):
    updates = []
    params = {"id": doc_id, "uid": user["id"], "team_id": user.get("team_id")}

    new_doc_type = (payload or {}).get("doc_type")
    if new_doc_type:
        updates.append("doc_type = :doc_type")
        params["doc_type"] = new_doc_type if new_doc_type in DOC_TYPES else "other"

    if "tags" in (payload or {}):
        tag_list = _parse_tags(payload.get("tags"))
        updates.append("tags = :tags")
        params["tags"] = json.dumps(tag_list)

    if "filename" in (payload or {}):
        new_name = sanitize_filename(payload.get("filename") or "")
        updates.append("filename = :filename")
        params["filename"] = new_name

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(updates + ["updated_at = CURRENT_TIMESTAMP"])
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            f"""
            UPDATE knowledge_documents
            SET {set_clause}
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            params,
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.post("/{doc_id}/extract")
async def trigger_extraction(doc_id: int, user=Depends(_require_user)):
    record = await _get_doc(doc_id, user, include_text=False)
    data = read_storage_bytes(record["storage_key"])
    processor = DocumentProcessor()
    extraction = processor.extract_text(data, record.get("mime"), record.get("filename"))
    status_flag = extraction.get("status") or "pending"
    if status_flag == "success":
        status_flag = "completed"
    extracted_text = extraction.get("text") if status_flag == "completed" else ""
    extraction_error = extraction.get("error") if status_flag != "completed" else None

    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            UPDATE knowledge_documents
            SET extracted_text = :extracted_text,
                extraction_status = :extraction_status,
                extraction_error = :extraction_error,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
              AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {
                "extracted_text": extracted_text,
                "extraction_status": status_flag,
                "extraction_error": extraction_error,
                "id": doc_id,
                "uid": user["id"],
                "team_id": user.get("team_id"),
            },
        )
    return {
        "ok": True,
        "extraction_status": status_flag,
        "metadata": extraction.get("metadata") or {},
        "error": extraction_error,
    }


@router.get("/{doc_id}/preview")
async def preview_extracted_text(doc_id: int, user=Depends(_require_user)):
    record = await _get_doc(doc_id, user, include_text=True)
    text = record.get("extracted_text") or ""
    return {
        "id": doc_id,
        "filename": record.get("filename"),
        "extracted_text": text[:4000],
        "extraction_status": record.get("extraction_status"),
        "extraction_error": record.get("extraction_error"),
    }
