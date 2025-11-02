from fastapi import APIRouter
from sqlalchemy import text
from app.db_core import engine

router = APIRouter(tags=["columbus_airports_detail"])

AIRPORTS_NAME = "Columbus Regional Airport Authority (CRAA)"

@router.get("/columbus_airports_detail/{solicitation_id}")
async def get_columbus_airports_detail(solicitation_id: str):

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
            {"ext": solicitation_id, "agency": AIRPORTS_NAME},
        )
        row = result.first()

    if not row:
        return {
            "error": "not_found",
            "rfq_id": solicitation_id,
            "agency": AIRPORTS_NAME,
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

    # build a friendly fallback body if we couldn't scrape description
    bits = []
    if status:
        bits.append(f"Status: {status}")
    if due_str:
        bits.append(f"Due: {due_str}")
    if posted_str:
        bits.append(f"Posted: {posted_str}")
    if source_url:
        bits.append(f"View / download docs on Columbus Airports portal: {source_url}")

    fallback_text = " | ".join(bits)
    scope_text = (description or "").strip() or fallback_text or "No additional details available."

    return {
        "rfq_id": external_id,
        "rfq_header_id": None,
        "title": title,
        "department": agency_name,
        "delivery_name": agency_name,
        "delivery_address": "",
        "due_date": due_str,
        "status_text": status,
        "solicitation_type": category or "Airport / Aviation",
        "scope_text": scope_text,
        "posted_date": posted_str,
        "source_url": source_url,
        "has_attachments": bool(attachments),
        "debug_keys": [],
    }
