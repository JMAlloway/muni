import json
import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.rfp_extractor import RfpExtractor
from app.services.extraction_cache import ExtractionCache
from app.storage import read_storage_bytes
from app.api.auth_helpers import require_user_with_team, ensure_user_can_access_opportunity

router = APIRouter(prefix="/api/rfp-extract", tags=["rfp-extract"])
cache = ExtractionCache()


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
async def extract_from_upload(upload_id: int, user=Depends(require_user_with_team)):
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
    await ensure_user_can_access_opportunity(user, rec["opportunity_id"])
    data = read_storage_bytes(rec["storage_key"])
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")

    processor = DocumentProcessor()
    extraction = processor.extract_text(data, rec.get("mime"), rec.get("filename"))
    text = extraction.get("text") or ""

    extractor = RfpExtractor()
    cached = await cache.get(text)
    if cached:
        extracted_all = cached
    else:
        extracted_all = extractor.extract_all(text)
        await cache.set(text, extracted_all)
    ts = datetime.datetime.utcnow().isoformat()
    # Wrap with versioning info
    payload = {
        "version": ts,
        "discovery": extracted_all.get("discovery") or {},
        "extracted": extracted_all.get("extracted") or {},
    }

    await _update_opportunity(rec["opportunity_id"], payload)

    return {
        "ok": True,
        "opportunity_id": rec["opportunity_id"],
        "extracted": payload,
    }
