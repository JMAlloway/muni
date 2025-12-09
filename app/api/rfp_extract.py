import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.rfp_extractor import RfpExtractor
from app.storage import read_storage_bytes

router = APIRouter(prefix="/api/rfp-extract", tags=["rfp-extract"])


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


async def _update_opportunity(opportunity_id: Any, extracted: Dict[str, Any]) -> None:
    """Best-effort update of both opportunities/opportunity tables."""
    async with engine.begin() as conn:
        for table in ("opportunities", "opportunity"):
            try:
                await conn.exec_driver_sql(
                    f"""
                    UPDATE {table}
                    SET summary = COALESCE(:summary, summary),
                        agency_name = COALESCE(:agency, agency_name),
                        json_blob = :json_blob,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :oid
                    """,
                    {
                        "summary": extracted.get("summary") or extracted.get("scope_of_work"),
                        "agency": extracted.get("agency"),
                        "json_blob": json.dumps(extracted),
                        "oid": opportunity_id,
                    },
                )
            except Exception:
                continue


@router.post("/{upload_id}")
async def extract_from_upload(upload_id: int, user=Depends(_require_user)):
    """
    Given an existing user_upload ID, extract structured RFP JSON and persist to the opportunity.
    """
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT id, user_id, opportunity_id, filename, mime, storage_key
            FROM user_uploads
            WHERE id = :id AND user_id = :uid
            """,
            {"id": upload_id, "uid": user["id"]},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")

    rec = row._mapping
    data = read_storage_bytes(rec["storage_key"])
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")

    processor = DocumentProcessor()
    extraction = processor.extract_text(data, rec.get("mime"), rec.get("filename"))
    text = extraction.get("text") or ""

    extractor = RfpExtractor()
    extracted_json = extractor.extract_json(text)

    await _update_opportunity(rec["opportunity_id"], extracted_json)

    return {
        "ok": True,
        "opportunity_id": rec["opportunity_id"],
        "extracted": extracted_json,
    }
