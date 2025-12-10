from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_helpers import ensure_user_can_access_opportunity, require_user_with_team
from app.core.db_core import engine
from app.services.question_extractor import extract_response_items
from app.storage import read_storage_bytes
from app.services.document_processor import DocumentProcessor

router = APIRouter(prefix="/api/opportunities", tags=["opportunity-questions"])


@router.get("/{opportunity_id}/detect-questions")
async def detect_questions(opportunity_id: str, user=Depends(require_user_with_team)):
    await ensure_user_can_access_opportunity(user, opportunity_id)
    # Fetch the latest instruction upload for this opportunity (if any)
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT storage_key, mime, filename
            FROM user_uploads
            WHERE opportunity_id = :oid
              AND user_id = :uid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"oid": opportunity_id, "uid": user["id"]},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="No uploads found for this opportunity")

    rec = row._mapping
    data = read_storage_bytes(rec["storage_key"])
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")

    processor = DocumentProcessor()
    extraction = processor.extract_text(data, rec.get("mime"), rec.get("filename"))
    text = extraction.get("text") or ""

    questions = extract_response_items(text)
    return {"questions": questions}
