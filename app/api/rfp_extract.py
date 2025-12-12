import json
import datetime
import logging
import asyncio
import time
from typing import Any, Dict, List
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.rfp_extractor import RfpExtractor
from app.services.extraction_cache import ExtractionCache
from app.storage import read_storage_bytes
from app.api.auth_helpers import require_user_with_team, ensure_user_can_access_opportunity
from app.api.uploads import ALLOWED_MIME, ALLOWED_EXT, MAX_BYTES

logger = logging.getLogger("rfp_extract")

router = APIRouter(prefix="/api/rfp-extract", tags=["rfp-extract"])
cache = ExtractionCache()
_rl_requests = defaultdict(deque)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 8  # requests per user per window

def _has_useful_content(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    extracted = payload.get("extracted") or payload
    if not isinstance(extracted, dict):
        return False
    fields = [
        extracted.get("summary"),
        extracted.get("scope_of_work"),
        extracted.get("submission_instructions"),
    ]
    lists = [
        extracted.get("required_documents") or [],
        extracted.get("required_forms") or [],
        extracted.get("compliance_terms") or [],
        extracted.get("deadlines") or [],
        extracted.get("contacts") or [],
    ]
    if any(f and str(f).strip() for f in fields):
        return True
    if any(isinstance(lst, list) and len(lst) for lst in lists):
        return True
    return False


def _check_rate_limit(user_id: Any, scope: str) -> None:
    now = time.time()
    dq = _rl_requests[(scope, user_id)]
    while dq and dq[0] < now - RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait and try again.")
    dq.append(now)


async def _update_opportunity(opportunity_id: Any, extracted: Dict[str, Any]) -> None:
    """Best-effort update of both opportunities/opportunity tables."""
    allowed_tables: List[str] = ["opportunities", "opportunity"]
    async with engine.begin() as conn:
        for table in allowed_tables:
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
                logger.exception("rfp_extract failed to update table=%s oid=%s", table, opportunity_id)
                continue


@router.post("/{upload_id}")
async def extract_from_upload(upload_id: int, user=Depends(require_user_with_team)) -> Dict[str, Any]:
    """
    Given an existing user_upload ID, extract structured RFP JSON and persist to the opportunity.
    """
    _check_rate_limit(user.get("id"), "rfp_extract")
    logger.info("rfp_extract start upload_id=%s user_id=%s", upload_id, user.get("id"))
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT id, user_id, opportunity_id, filename, mime, storage_key, size
            FROM user_uploads
            WHERE id = :id AND user_id = :uid
            """,
            {"id": upload_id, "uid": user["id"]},
        )
        row = res.first()
    if not row:
        logger.warning("rfp_extract upload not found upload_id=%s", upload_id)
        raise HTTPException(status_code=404, detail="Upload not found")

    rec = row._mapping
    await ensure_user_can_access_opportunity(user, rec["opportunity_id"])
    size = rec.get("size") or 0
    if size and size > MAX_BYTES:
        logger.warning("rfp_extract file too large upload_id=%s size=%s", upload_id, size)
        raise HTTPException(status_code=413, detail="File too large")

    # Basic MIME/extension validation
    mime = (rec.get("mime") or "").lower().strip()
    ext = (rec.get("filename") or "").split(".")[-1].lower() if rec.get("filename") else ""
    if mime and mime not in ALLOWED_MIME and ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    data = await asyncio.to_thread(read_storage_bytes, rec["storage_key"])
    if not data:
        logger.warning("rfp_extract empty file upload_id=%s", upload_id)
        raise HTTPException(status_code=400, detail="File is empty")

    processor = DocumentProcessor()
    extraction = processor.extract_text(data, mime, rec.get("filename"))
    text = extraction.get("text") or ""
    logger.info(
      "rfp_extract extracted_text bytes=%s mime=%s filename=%s",
      len(text.encode("utf-8")) if text else 0,
      rec.get("mime"),
      rec.get("filename"),
    )

    extractor = RfpExtractor()
    cached = await cache.get(text)
    extracted_all = cached if cached else None
    if cached:
        if _has_useful_content(cached):
            logger.info("rfp_extract cache_hit upload_id=%s", upload_id)
        else:
            logger.info("rfp_extract cache_miss_due_to_empty upload_id=%s", upload_id)
            extracted_all = None
    if extracted_all is None:
        try:
            extracted_all = await asyncio.wait_for(asyncio.to_thread(extractor.extract_all, text), timeout=120)
        except asyncio.TimeoutError:
            logger.error("rfp_extract timeout upload_id=%s", upload_id)
            raise HTTPException(status_code=504, detail="Extraction timed out")
        except Exception as exc:
            logger.error("rfp_extract failed upload_id=%s error=%s", upload_id, exc)
            raise HTTPException(status_code=500, detail="Extraction failed")

        if not isinstance(extracted_all, dict):
            raise HTTPException(status_code=500, detail="Extraction failed (invalid response)")

        if _has_useful_content(extracted_all):
            await cache.set(text, extracted_all)
            logger.info("rfp_extract cache_store upload_id=%s", upload_id)
        else:
            logger.warning("rfp_extract empty_extraction upload_id=%s", upload_id)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Wrap with versioning info
    payload = {
        "version": ts,
        "discovery": extracted_all.get("discovery") or {},
        "extracted": extracted_all.get("extracted") or {},
    }
    warning = None
    if not _has_useful_content(payload):
        warning = "Extraction returned no summary/checklist/dates. Try rerunning or upload a clearer document."
        logger.warning("rfp_extract warning_no_content upload_id=%s", upload_id)

    await _update_opportunity(rec["opportunity_id"], payload)
    logger.info(
        "rfp_extract complete upload_id=%s opportunity_id=%s discovery_keys=%s extracted_keys=%s",
        upload_id,
        rec["opportunity_id"],
        list((payload.get("discovery") or {}).keys()),
        list((payload.get("extracted") or {}).keys()),
    )

    return {
        "ok": True,
        "opportunity_id": rec["opportunity_id"],
        "extracted": payload,
        "warning": warning,
    }
