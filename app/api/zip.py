from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from io import BytesIO
import zipfile, os
from app.core.db_core import engine
from app.auth.session import get_current_user_email
from app.storage import USE_S3, BUCKET, _s3

router = APIRouter(prefix="/zip", tags=["zip"])

async def _require_user(request: Request):
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(text("SELECT id, email FROM users WHERE email = :e LIMIT 1"), {"e": email})
        row = res.first()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    m = row._mapping
    class U: pass
    u = U(); u.id = m["id"]; u.email = m["email"]
    return u

@router.get("/{opportunity_id}")
async def zip_for_opportunity(opportunity_id: int, user = Depends(_require_user)):
    q = (
        """
        SELECT filename, storage_key
        FROM user_uploads
        WHERE user_id = :uid AND opportunity_id = :oid
        ORDER BY created_at ASC
        """
    )
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(q, {"uid": user.id, "oid": opportunity_id})
        rows = res.fetchall()

    if not rows:
        raise HTTPException(404, "No files")

    def stream():
        buf = BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for r in rows:
                filename = r._mapping["filename"]
                key = r._mapping["storage_key"]
                if USE_S3:
                    obj = _s3.get_object(Bucket=BUCKET, Key=key)
                    data = obj["Body"].read()
                else:
                    with open(key, "rb") as f:
                        data = f.read()
                zf.writestr(filename or os.path.basename(key), data)
        buf.seek(0)
        yield from buf

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="opportunity_{opportunity_id}.zip"'}
    )
