from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
import os
from sqlalchemy import text
from app.core.db_core import engine
from app.auth import get_current_user
from app.storage import store_bytes, create_presigned_get, USE_S3, BUCKET

if USE_S3:
    import boto3
    _s3 = boto3.client("s3")

router = APIRouter(prefix="/uploads", tags=["uploads"])

@router.post("/add")
async def upload_files(
    opportunity_id: int = Form(...),
    files: List[UploadFile] = File(...),
    user = Depends(get_current_user)
):
    saved = []
    async with engine.begin() as conn:
        for up in files:
            data = await up.read()
            if not data:
                continue
            # TODO (optional): enforce size/MIME allowlist here
            storage_key, size, mime = store_bytes(user.id, opportunity_id, data, up.filename, up.content_type)
            await conn.exec_driver_sql(text("""
                INSERT INTO user_uploads (user_id, opportunity_id, filename, mime, size, storage_key)
                VALUES (:uid, :oid, :fn, :mime, :size, :key)
            """), {"uid": user.id, "oid": opportunity_id, "fn": up.filename, "mime": mime, "size": size, "key": storage_key})
            # get inserted row id
            row = await conn.exec_driver_sql(text("SELECT last_insert_rowid() AS id"))
            rec_id = row.first()[0]
            saved.append({
                "id": rec_id,
                "filename": up.filename,
                "size": size,
                "mime": mime,
                "download_url": create_presigned_get(storage_key)
            })
    return {"ok": True, "files": saved}

@router.get("/list/{opportunity_id}")
async def list_uploads(opportunity_id: int, user = Depends(get_current_user)):
    q = text("""
        SELECT id, filename, mime, size, storage_key, created_at
        FROM user_uploads
        WHERE user_id = :uid AND opportunity_id = :oid
        ORDER BY created_at DESC
    """)
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(q, {"uid": user.id, "oid": opportunity_id})
        rows = [dict(r._mapping) for r in res.fetchall()]
    for r in rows:
        r["download_url"] = create_presigned_get(r["storage_key"])
    return rows

@router.delete("/{upload_id}")
async def delete_upload(upload_id: int, user = Depends(get_current_user)):
    # NOTE: we only delete the record (safe, since files could be shared later).
    q = text("DELETE FROM user_uploads WHERE id = :id AND user_id = :uid")
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(q, {"id": upload_id, "uid": user.id})
    return {"ok": True}

# Local-only streaming (S3 uses pre-signed URL)
@router.get("/local/{path:path}")
async def get_local_file(path: str, user = Depends(get_current_user)):
    if USE_S3:
        raise HTTPException(404, "S3 mode")
    # Security: force within uploads/
    if not path.startswith("uploads" + os.sep):
        path = os.path.join("uploads", path)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing")

    def iterfile():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk: break
                yield chunk

    return StreamingResponse(iterfile(), media_type="application/octet-stream")
