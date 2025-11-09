# app/routers/cota_detail.py

from fastapi import APIRouter
from sqlalchemy import text
from app.core.db_core import engine

router = APIRouter(tags=["cota_detail"])

COTA_NAME = "Central Ohio Transit Authority (COTA)"


@router.get("/cota_detail/{solicitation_id}")
async def get_cota_detail(solicitation_id: str):
    """
    Fetch a single COTA opportunity from the DB and return detail JSON
    shaped like columbus_detail for the modal.

    This version assumes the `opportunities` table now has:
      - description (TEXT)
      - attachments (TEXT or NULL)
    """

    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    external_id,
                    title,
                    agency_name,
                    due_date,
                    posted_date,
                    source_url,
                    status,
                    category,
                    description,
                    attachments
                FROM opportunities
                WHERE external_id = :ext
                  AND agency_name = :agency
                LIMIT 1
                """
            ),
            {"ext": solicitation_id, "agency": COTA_NAME},
        )
        row = result.first()

    if not row:
        return {
            "error": "not_found",
            "rfq_id": solicitation_id,
            "agency": COTA_NAME,
        }

    (
        external_id,
        title,
        agency_name,
        due_date,
        posted_date,
        source_url,
        status,
        category,
        description,
        attachments,
    ) = row

    def _fmt(dt):
        if not dt:
            return ""
        try:
            return dt.strftime("%m/%d/%Y %I:%M %p")
        except Exception:
            return str(dt)

    due_str = _fmt(due_date)
    posted_str = _fmt(posted_date)

    # scope_text is literally the long narrative we stored at ingest time
    scope_text = description or ""

    has_attachments = bool(attachments)

    return {
        "rfq_id": external_id,
        "rfq_header_id": None,
        "title": title,
        "department": agency_name,
        "delivery_name": agency_name,
        "delivery_address": "",
        "due_date": due_str,
        "status_text": status,
        "solicitation_type": category or "Transit / Transportation",
        "scope_text": scope_text,
        "posted_date": posted_str,
        "source_url": source_url,
        "has_attachments": has_attachments,
        "debug_keys": [],
    }
