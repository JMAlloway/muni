import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Optional

from app.ingest.base import RawOpportunity
from app.ingest.municipalities.columbus_metropolitan_library import (
    _clean_ws,
    _extract_meta_from_pdf_bytes,
)

AGENCY_NAME = "Columbus Metropolitan Housing Authority"

# This is the base domain for building absolute attachment URLs
BASE_URL = "https://cmhanet.com"

# This is the live Purchasing page you grabbed HTML from
PURCHASING_URL = f"{BASE_URL}/purchasing"


def _parse_solicitation(text: str):
    """Extract solicitation ID and title."""
    text = _clean_ws(text.replace("–", "-"))
    m = re.search(r"(\d{4}-\d{3})", text)
    solicitation_id = m.group(1) if m else ""
    title = text
    if solicitation_id:
        title = text.replace(solicitation_id, "").strip(" -:")
    return solicitation_id, title


def fetch() -> List[RawOpportunity]:
    resp = requests.get(PURCHASING_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    opportunities: List[RawOpportunity] = []

    # Find all purchase-item blocks under "Current RFP/RFQ/IFB"
    for item in soup.select(".current-projects .purchase-item"):
        h4 = item.find("h4")
        if not h4:
            continue

        headline = _clean_ws(h4.get_text(" ", strip=True))
        solicitation_id, title = _parse_solicitation(headline)

        # Collect attachments (RFP PDF, addenda, etc.)
        attachments = []
        for a in item.find_all("a", href=True):
            url = a["href"]
            if not url.lower().startswith("http"):
                url = f"{BASE_URL}{url}"
            attachments.append({
                "label": _clean_ws(a.get_text(" ", strip=True)),
                "url": url,
            })

        # If there's an Award Notice link, this opportunity is done. Skip it.
        has_award_notice = any(
            "award" in att["label"].lower()
            and "notice" in att["label"].lower()
            for att in attachments
        )
        if has_award_notice:
            # don't include closed/awarded rows at all
            continue

        # Otherwise, we treat it as active ("open")
        status = "open"

        # --- Pull metadata from the first attachment PDF ---
        posted_date_dt: Optional[datetime] = None
        due_date_dt: Optional[datetime] = None
        description_text = ""

        core_pdf_url = attachments[0]["url"] if attachments else f"{PURCHASING_URL}#{solicitation_id}"
        if core_pdf_url.lower().endswith(".pdf"):
            try:
                pdf_resp = requests.get(core_pdf_url, timeout=20)
                if pdf_resp.status_code == 200:
                    posted_date_dt, due_date_dt, desc_from_pdf = _extract_meta_from_pdf_bytes(
                        pdf_resp.content
                    )
                    if desc_from_pdf:
                        description_text = desc_from_pdf
            except requests.RequestException:
                pass

        # Fallbacks
        if posted_date_dt is None:
            posted_date_dt = datetime.utcnow()

        if due_date_dt is None:
            description_text = (
                (description_text + "\n" if description_text else "")
                + "⚠ Unable to auto-read due date from PDF. Please review manually."
            )

        # --- Build the RawOpportunity ---
        opp = RawOpportunity(
            source="cmha",
            source_url=core_pdf_url,
            title=title or headline,
            summary="",
            description=description_text.strip(),
            category=headline.split()[0] if headline else "",
            agency_name=AGENCY_NAME,
            location_geo="Columbus, OH",
            posted_date=posted_date_dt,
            due_date=due_date_dt,
            prebid_date=None,
            attachments=attachments,
            status=status,  # always "open" now, because we've filtered out awarded
            hash_body=None,
            external_id=solicitation_id or "",
            keyword_tag="",
            date_added=datetime.now(timezone.utc),  # 👈 NEW LINE
        )

        opportunities.append(opp)

    return opportunities

