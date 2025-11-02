# app/routers/gahanna_detail.py

from fastapi import APIRouter
from sqlalchemy import text
from app.db_core import engine

router = APIRouter(tags=["gahanna_detail"])

GAHANNA_NAME = "City of Gahanna"


@router.get("/gahanna_detail/{solicitation_id}")
async def get_gahanna_detail(solicitation_id: str):
    """
    Fetch a single Gahanna opportunity from the DB and return JSON
    in the same shape as the COTA modal uses.
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
            {"ext": solicitation_id, "agency": GAHANNA_NAME},
        )
        row = result.first()

    if not row:
        return {
            "error": "not_found",
            "rfq_id": solicitation_id,
            "agency": GAHANNA_NAME,
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
        "solicitation_type": category or "General / City Bid",
        "scope_text": scope_text,
        "posted_date": posted_str,
        "source_url": source_url,
        "has_attachments": has_attachments,
        "debug_keys": [],
    }
