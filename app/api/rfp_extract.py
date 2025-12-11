import json
import datetime
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.rfp_extractor import RfpExtractor
from app.services.extraction_cache import ExtractionCache
from app.storage import read_storage_bytes
from app.api.auth_helpers import require_user_with_team, ensure_user_can_access_opportunity

logger = logging.getLogger(__name__)

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
    logger.info("[rfp_extract] Starting extraction for upload_id=%s, user=%s", upload_id, user.get("id"))
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
        logger.warning("[rfp_extract] Upload not found: upload_id=%s, user=%s", upload_id, user.get("id"))
        raise HTTPException(status_code=404, detail="Upload not found")

    rec = row._mapping
    await ensure_user_can_access_opportunity(user, rec["opportunity_id"])
    data = read_storage_bytes(rec["storage_key"])
    if not data:
        logger.warning("[rfp_extract] File is empty: upload_id=%s", upload_id)
        raise HTTPException(status_code=400, detail="File is empty")

    logger.info("[rfp_extract] Processing document: filename=%s, mime=%s, size=%d bytes",
                rec.get("filename"), rec.get("mime"), len(data))
    processor = DocumentProcessor()
    extraction = processor.extract_text(data, rec.get("mime"), rec.get("filename"))
    text = extraction.get("text") or ""
    extraction_status = extraction.get("status", "unknown")
    extraction_error = extraction.get("error")
    logger.info("[rfp_extract] Text extraction result: status=%s, text_length=%d, error=%s",
                extraction_status, len(text), extraction_error)

    # Build warning messages for frontend
    warnings = []
    if not text.strip():
        logger.warning("[rfp_extract] No text extracted from document - may be scanned PDF or unsupported format")
        warnings.append("No text could be extracted from this document. It may be a scanned PDF without OCR, or an unsupported format.")
    elif len(text.strip()) < 100:
        warnings.append(f"Very little text extracted ({len(text.strip())} characters). Results may be incomplete.")

    extractor = RfpExtractor()
    cached = await cache.get(text)

    # Don't use cached empty results - force re-extraction
    if cached:
        cached_extracted = cached.get("extracted") or {}
        has_cached_content = bool(
            cached_extracted.get("summary") or
            cached_extracted.get("scope_of_work") or
            cached_extracted.get("required_documents") or
            cached_extracted.get("deadlines")
        )
        if has_cached_content:
            logger.info("[rfp_extract] Using cached extraction result (has content)")
            extracted_all = cached
        else:
            logger.info("[rfp_extract] Ignoring cached empty result, running fresh extraction")
            cached = None

    if not cached:
        logger.info("[rfp_extract] Running fresh extraction")
        extracted_all = extractor.extract_all(text)

        # Only cache if we got actual content
        extracted_data = extracted_all.get("extracted") or {}
        has_content = bool(
            extracted_data.get("summary") or
            extracted_data.get("scope_of_work") or
            extracted_data.get("required_documents") or
            extracted_data.get("deadlines")
        )
        if has_content:
            await cache.set(text, extracted_all)
            logger.info("[rfp_extract] Cached extraction result")
        else:
            logger.warning("[rfp_extract] Not caching empty extraction result")
            warnings.append("AI extraction returned no results. This may indicate the document format is not recognized or the AI service is unavailable.")

    ts = datetime.datetime.utcnow().isoformat()
    # Wrap with versioning info
    payload = {
        "version": ts,
        "discovery": extracted_all.get("discovery") or {},
        "extracted": extracted_all.get("extracted") or {},
    }

    # Log what we're returning
    extracted_data = payload.get("extracted") or {}
    logger.info("[rfp_extract] Extraction complete - summary=%s, deadlines=%d, required_docs=%d",
                bool(extracted_data.get("summary")),
                len(extracted_data.get("deadlines") or []),
                len(extracted_data.get("required_documents") or []))

    await _update_opportunity(rec["opportunity_id"], payload)

    return {
        "ok": True,
        "opportunity_id": rec["opportunity_id"],
        "extracted": payload,
        "warnings": warnings if warnings else None,
        "text_extracted": len(text.strip()) > 0,
        "text_length": len(text.strip()),
    }
