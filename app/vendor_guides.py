# app/vendor_guides.py
import datetime
import re
import textwrap
from typing import Optional, Tuple

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text as sql_text

from app.core.db_core import engine
from app.ai.client import get_llm_client

COLUMBUS_VENDOR_URL = (
    "https://www.columbus.gov/Business-Development/Bids-Solicitations/Vendor-Resources"
)

COLUMBUS_FALLBACK_TXT = textwrap.dedent(
    """
    City of Columbus – Vendor Resources

    1. Register as a vendor: go to https://vendors.columbus.gov and create an account.
    2. Find current bids / solicitations on the City website.
    3. Download the solicitation package and any required forms (EBO, insurance, bid bond).
    4. Complete the forms and upload/submit before the deadline. Late bids are not accepted.
    5. Keep your contact and tax info (W-9) up to date in the portal.
    """
).strip()


def _slugify_agency(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln])


async def fetch_columbus_vendor_page() -> Tuple[str, str]:
    """Return (raw_html, extracted_text), falling back if blocked."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(COLUMBUS_VENDOR_URL, headers={"Accept": "text/html,application/xhtml+xml"})
        if resp.status_code == 200 and resp.text:
            html = resp.text
            extracted = _extract_text_from_html(html)
            return html, extracted
        return COLUMBUS_FALLBACK_TXT, COLUMBUS_FALLBACK_TXT
    except Exception:
        return COLUMBUS_FALLBACK_TXT, COLUMBUS_FALLBACK_TXT


def _build_prompt(agency_name: str, source_text: str) -> str:
    return textwrap.dedent(
        f"""
        You are helping a small business submit a bid or RFP response to **{agency_name}**.

        Below is the official vendor/resources text:

        ---
        {source_text}
        ---

        Rewrite this as a short, clear, plain-English guide with these sections:

        ### Who needs to do this
        ### Step-by-step
        ### Documents to have ready (W-9, bid form, certifications, insurance, bid bond if required)
        ### Where to submit / portal
        ### Deadline rules
        ### Helpful links

        Tone: friendly, clear, 8th grade reading level.
        Output as markdown.
        """
    ).strip()


async def build_llm_summary(agency_name: str, extracted_text: str) -> str:
    llm = get_llm_client()
    if llm is None:
        # fallback: just chop source
        return textwrap.shorten(extracted_text, width=1500, placeholder=" …")

    prompt = _build_prompt(agency_name, extracted_text)
    resp = llm.chat(
        [
            {"role": "system", "content": "You are an expert in municipal procurement."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return resp


async def upsert_vendor_guide_for_columbus() -> dict:
    agency_name = "City of Columbus"
    agency_slug = _slugify_agency(agency_name)

    raw_html, extracted = await fetch_columbus_vendor_page()
    llm_summary = await build_llm_summary(agency_name, extracted)
    now = datetime.datetime.utcnow().isoformat()

    async with engine.begin() as conn:
        await conn.execute(
            sql_text(
                """
                INSERT INTO vendor_guides (
                    agency_name, agency_slug, source_url,
                    raw_html, extracted_text, llm_summary, updated_at
                )
                VALUES (
                    :agency_name, :agency_slug, :source_url,
                    :raw_html, :extracted_text, :llm_summary, :updated_at
                )
                ON CONFLICT(agency_slug) DO UPDATE SET
                    raw_html = excluded.raw_html,
                    extracted_text = excluded.extracted_text,
                    llm_summary = excluded.llm_summary,
                    source_url = excluded.source_url,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "agency_name": agency_name,
                "agency_slug": agency_slug,
                "source_url": COLUMBUS_VENDOR_URL,
                "raw_html": raw_html,
                "extracted_text": extracted,
                "llm_summary": llm_summary,
                "updated_at": now,
            },
        )

    return {
        "agency_name": agency_name,
        "agency_slug": agency_slug,
        "source_url": COLUMBUS_VENDOR_URL,
        "llm_summary": llm_summary,
        "updated_at": now,
    }


async def get_vendor_guide_by_slug(slug: str) -> Optional[dict]:
    async with engine.begin() as conn:
        res = await conn.execute(
            sql_text(
                """
                SELECT agency_name, agency_slug, source_url,
                       llm_summary, updated_at
                FROM vendor_guides
                WHERE agency_slug = :slug
                """
            ),
            {"slug": slug},
        )
        row = res.fetchone()

    if not row:
        return None

    return {
        "agency_name": row[0],
        "agency_slug": row[1],
        "source_url": row[2],
        "llm_summary": row[3],
        "updated_at": row[4],
    }
