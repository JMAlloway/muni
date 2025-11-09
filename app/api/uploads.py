from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from typing import List
import os, uuid, re
from pathlib import Path
from sqlalchemy import text
from app.core.db_core import engine
from app.auth import require_admin
from app.auth.session import get_current_user_email
from app.storage import store_bytes, create_presigned_get, USE_S3, BUCKET, LOCAL_DIR, _s3

if USE_S3:
    # _s3 provided by app.storage (configured for custom endpoints like R2)
    pass

router = APIRouter(prefix="/uploads", tags=["uploads"])


# Session-cookie auth helper (same logic as bid_tracker)
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
    # namedtuple-like row; provide attributes for convenience
    class U: pass
    u = U(); u.id = m["id"]; u.email = m["email"]
    return u


async def _resolve_opportunity_id(key: str) -> int:
    """Accept numeric internal id or external_id string; return internal id."""
    async with engine.begin() as conn:
        if key and str(key).isdigit():
            res = await conn.exec_driver_sql(
                "SELECT id FROM opportunities WHERE id = :k LIMIT 1",
                {"k": int(key)},
            )
            row = res.first()
            if row:
                return row[0]
        res = await conn.exec_driver_sql(
            "SELECT id FROM opportunities WHERE external_id = :k OR CAST(id AS TEXT) = :k LIMIT 1",
            {"k": str(key)},
        )
        row = res.first()
        if row:
            return row[0]
    raise HTTPException(status_code=404, detail="Opportunity not found")

@router.post("/add")
async def upload_files(
    opportunity_id: str = Form(...),
    files: List[UploadFile] = File(...),
    user = Depends(_require_user)
):
    saved = []
    oid = await _resolve_opportunity_id(opportunity_id)
    async with engine.begin() as conn:
        for up in files:
            # Enforce MIME/size/filename hygiene
            safe_name = sanitize_filename(up.filename)
            mime = (up.content_type or "").lower().strip()
            if mime and mime not in ALLOWED_MIME:
                # allow unknown mime if extension permitted
                ext = Path(safe_name).suffix.lower().lstrip(".")
                if ext not in ALLOWED_EXT:
                    raise HTTPException(status_code=400, detail=f"Unsupported file type: {mime or ext}")

            data = await up.read()
            if not data:
                continue
            if len(data) > MAX_BYTES:
                raise HTTPException(status_code=413, detail=f"File too large (>{MAX_UPLOAD_MB} MB)")

            storage_key, size, mime = store_bytes(user.id, oid, data, safe_name, mime)
            await conn.exec_driver_sql("""
                INSERT INTO user_uploads (user_id, opportunity_id, filename, mime, size, storage_key)
                VALUES (:uid, :oid, :fn, :mime, :size, :key)
            """, {"uid": user.id, "oid": oid, "fn": safe_name, "mime": mime, "size": size, "key": storage_key})
            # get inserted row id
            row = await conn.exec_driver_sql("SELECT last_insert_rowid() AS id")
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
async def list_uploads(opportunity_id: str, user = Depends(_require_user)):
    oid = await _resolve_opportunity_id(opportunity_id)
    q = """
        SELECT id, filename, mime, size, storage_key, created_at
        FROM user_uploads
        WHERE user_id = :uid AND opportunity_id = :oid
        ORDER BY created_at DESC
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(q, {"uid": user.id, "oid": oid})
        rows = [dict(r._mapping) for r in res.fetchall()]
    for r in rows:
        r["download_url"] = create_presigned_get(r["storage_key"])
    return rows

@router.delete("/{upload_id}")
async def delete_upload(upload_id: int, user = Depends(_require_user)):
    # Fetch the storage key first
    async with engine.begin() as conn:
        row = await conn.exec_driver_sql(
            "SELECT storage_key FROM user_uploads WHERE id = :id AND user_id = :uid",
            {"id": upload_id, "uid": user.id},
        )
        rec = row.first()
        if not rec:
            raise HTTPException(404, "Not found")
        storage_key = rec._mapping["storage_key"]

        # Delete the record
        await conn.exec_driver_sql(
            "DELETE FROM user_uploads WHERE id = :id AND user_id = :uid",
            {"id": upload_id, "uid": user.id},
        )

        # Check if any other rows reference this key
        row2 = await conn.exec_driver_sql(
            "SELECT COUNT(1) AS c FROM user_uploads WHERE storage_key = :k",
            {"k": storage_key},
        )
        remaining = row2.first()[0]

    # If no references remain, delete the underlying object
    if remaining == 0 and storage_key:
        try:
            if USE_S3:
                _s3.delete_object(Bucket=BUCKET, Key=storage_key)
            else:
                # Guard against path traversal; force inside LOCAL_DIR
                base = os.path.abspath(LOCAL_DIR)
                abspath = os.path.abspath(storage_key)
                if abspath.startswith(base) and os.path.exists(abspath):
                    os.remove(abspath)
        except Exception:
            # Swallow deletion errors to avoid breaking UX; file will be orphaned
            pass

    return {"ok": True}


@router.patch("/{upload_id}")
async def rename_upload(upload_id: int, payload: dict, user = Depends(_require_user)):
    """Rename a previously uploaded file (current user only)."""
    new_name = (payload or {}).get("filename", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="filename required")
    if len(new_name) > 255:
        raise HTTPException(status_code=400, detail="filename too long")

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "UPDATE user_uploads SET filename = :fn WHERE id = :id AND user_id = :uid",
            {"fn": new_name, "id": upload_id, "uid": user.id},
        )
    return {"ok": True}


@router.get("/stats", response_class=StreamingResponse)
async def uploads_stats(admin = Depends(require_admin)):
    """Simple admin-only stats page with totals and largest files."""
    # Aggregate stats
    async with engine.begin() as conn:
        total_row = await conn.exec_driver_sql(
            text("SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes FROM user_uploads")
        )
        n, total_bytes = total_row.first()
        top_rows = await conn.exec_driver_sql(
            text(
                """
                SELECT u.id, u.filename, u.size, u.mime, u.created_at, o.title, u.storage_key
                FROM user_uploads u
                LEFT JOIN opportunities o ON o.id = u.opportunity_id
                ORDER BY u.size DESC
                LIMIT 20
                """
            )
        )
        top = [dict(r._mapping) for r in top_rows.fetchall()]

    def fmt_bytes(b: int) -> str:
        b = int(b or 0)
        for unit in ["B","KB","MB","GB","TB"]:
            if b < 1024 or unit == "TB":
                return f"{b:.1f} {unit}" if unit != "B" else f"{b} B"
            b /= 1024
        return f"{b} B"

    html = [
        "<section class='card' style='padding:16px;'>",
        "<h2>Uploads Stats</h2>",
        f"<div>Total files: <b>{n}</b></div>",
        f"<div>Total storage (from DB sizes): <b>{fmt_bytes(total_bytes)}</b></div>",
        f"<div>Storage backend: <code>{'S3' if USE_S3 else 'Local disk'}</code></div>",
        f"<div>Bucket: <code>{BUCKET if USE_S3 else LOCAL_DIR}</code></div>",
        "<h3 style='margin-top:12px;'>Largest 20 files</h3>",
        "<table style='width:100%; border-collapse:collapse;'>",
        "<thead><tr><th style='text-align:left;'>Filename</th><th style='text-align:right;'>Size</th><th style='text-align:left;'>Type</th><th style='text-align:left;'>Opportunity</th><th style='text-align:left;'>Created</th></tr></thead>",
        "<tbody>",
    ]
    for r in top:
        html.append(
            f"<tr><td>{(r.get('filename') or '').replace('<','&lt;')}</td>"
            f"<td style='text-align:right;'>{fmt_bytes(r.get('size') or 0)}</td>"
            f"<td>{(r.get('mime') or '')}</td>"
            f"<td>{(r.get('title') or '')}</td>"
            f"<td>{(r.get('created_at') or '')}</td></tr>"
        )
    html.extend(["</tbody></table>", "</section>"])

    def stream():
        yield "".join(html)

    return StreamingResponse(stream(), media_type="text/html")

# Local-only streaming (S3 uses pre-signed URL)
@router.get("/local/{path:path}")
async def get_local_file(path: str, user = Depends(_require_user)):
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


@router.get("/health")
async def uploads_health(admin = Depends(require_admin)):
    """Admin-only health check for storage backend.
    S3/R2: put -> get -> delete a tiny object.
    Local: write -> read -> delete a tiny file.
    """
    details = {
        "backend": "s3" if USE_S3 else "local",
        "bucket": BUCKET if USE_S3 else None,
        "local_dir": None if USE_S3 else os.path.abspath(LOCAL_DIR),
    }
    try:
        payload = b"health-ok"
        if USE_S3:
            key = f"healthcheck/{uuid.uuid4()}.txt"
            _s3.put_object(Bucket=BUCKET, Key=key, Body=payload, ContentType="text/plain")
            obj = _s3.get_object(Bucket=BUCKET, Key=key)
            data = obj["Body"].read()
            _s3.delete_object(Bucket=BUCKET, Key=key)
            ok = data == payload
            details.update({"key": key, "read_len": len(data)})
        else:
            folder = os.path.join(LOCAL_DIR, "healthcheck")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{uuid.uuid4()}.txt")
            with open(path, "wb") as f:
                f.write(payload)
            with open(path, "rb") as f:
                data = f.read()
            try:
                os.remove(path)
            except OSError:
                pass
            ok = data == payload
            details.update({"path": os.path.abspath(path), "read_len": len(data)})

        if not ok:
            return {"ok": False, "error": "payload mismatch", "details": details}, status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"ok": True, "details": details}
    except Exception as e:
        return {"ok": False, "error": str(e), "details": details}, status.HTTP_500_INTERNAL_SERVER_ERROR
# --- Upload constraints & helpers ---
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25").strip() or 25)
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_MIME = {
    # documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    # images
    "image/jpeg", "image/png", "image/gif", "image/webp",
}
ALLOWED_EXT = {"pdf","doc","docx","xls","xlsx","ppt","pptx","txt","csv","jpg","jpeg","png","gif","webp"}

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
def sanitize_filename(name: str) -> str:
    name = os.path.basename(name or "")
    if not name:
        return f"file-{uuid.uuid4().hex}"
    stem = Path(name).stem
    ext = Path(name).suffix.lower().lstrip(".")
    stem = _SAFE_RE.sub("-", stem).strip("-._") or f"file-{uuid.uuid4().hex}"
    if ext and ext not in ALLOWED_EXT:
        # drop unknown extension; store without it (or store_bytes may add MIME-based)
        ext = ""
    out = stem[:80]
    return f"{out}.{ext}" if ext else out
