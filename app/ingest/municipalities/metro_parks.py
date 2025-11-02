import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.ingest.base import RawOpportunity
from app.ingest.municipalities.columbus_metropolitan_library import (
    _clean_ws,
    _extract_meta_from_pdf_bytes,
)

AGENCY_NAME = "Columbus and Franklin County Metro Parks"
BASE_URL = "https://www.metroparks.net"
BIDDING_URL = f"{BASE_URL}/about-us/contract-bidding/"


def _guess_external_id(text: str) -> str:
    t = text.upper()

    m_year = re.search(r"\b(20\d{2})\b", t)
    if m_year:
        return m_year.group(1)

    m_rfp = re.search(r"\bRFP[^\s]{0,20}", t)
    if m_rfp:
        return m_rfp.group(0)

    return ""


def _extract_meta_plus_due(pdf_bytes: bytes) -> Tuple[datetime, Optional[datetime], str, Optional[str]]:
    """
    Wraps _extract_meta_from_pdf_bytes and then scans for a human due line.
    Returns:
      posted_date_dt (datetime)           -- always set (falls back to now)
      due_date_dt (datetime or None)      -- parsed datetime if we can parse it
      description_text (str)              -- overview text slice from PDF
      due_text_raw (str or None)          -- e.g. 'Due Date: November 3, 2025 5PM'
    """
    posted_date_dt, due_date_dt, desc_from_pdf = _extract_meta_from_pdf_bytes(pdf_bytes)

    # Decode full text so we can find "Due Date: November 3, 2025 5PM"
    try:
        full_txt = pdf_bytes.decode("utf-8", errors="ignore")
    except Exception:
        full_txt = pdf_bytes.decode("latin-1", errors="ignore")

    due_text_raw = None
    for raw_line in full_txt.splitlines():
        line_clean = _clean_ws(raw_line)
        low = line_clean.lower()

        # We care about explicit due info, not TBD now
        # Look for 'due' AND something that looks like a month/day/year or mm/dd/yyyy
        if "due" in low or "submission" in low or "bid opening" in low:
            # If the line has a real date like "November 3, 2025 5PM" or "11/03/2025 5PM"
            if re.search(r"\b(?:[A-Za-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4})", line_clean):
                due_text_raw = line_clean
                break

            # If the line literally says TBD we'll capture that too for transparency
            if "tbd" in low:
                due_text_raw = line_clean
                break

    # make sure posted_date_dt always exists because we sort on it
    if posted_date_dt is None:
        posted_date_dt = datetime.utcnow()

    return posted_date_dt, due_date_dt, desc_from_pdf or "", due_text_raw


def fetch() -> List[RawOpportunity]:
    resp = requests.get(BIDDING_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    opportunities: List[RawOpportunity] = []

    # Only scrape the "Projects in Progress" accordion, ignore "Bid Results"
    prog_panel = soup.select_one("#projects-in-progress")
    if not prog_panel:
        return opportunities

    body = prog_panel.select_one(".vc_tta-panel-body")
    if not body:
        return opportunities

    link_tags = body.select("p > a[href]")
    if not link_tags:
        return opportunities

    # Build full attachment list
    attachments = []
    for a in link_tags:
        label = _clean_ws(a.get_text(" ", strip=True))
        url = a["href"]
        if not url.lower().startswith("http"):
            url = f"{BASE_URL}{url}"
        attachments.append({
            "label": label,
            "url": url,
        })

    # We'll consider the FIRST link text our "headline", for title/external_id
    first_label = attachments[0]["label"]
    first_url = attachments[0]["url"]

    # Create a nice clean title from the first label
    nice_title = first_label
    nice_title = re.sub(r"\bRFP\b.*", "", nice_title, flags=re.IGNORECASE)
    nice_title = re.sub(r"\bProposal Document\b.*", "", nice_title, flags=re.IGNORECASE)
    nice_title = re.sub(r"\bPublic Notice\b.*", "", nice_title, flags=re.IGNORECASE)
    nice_title = nice_title.replace("_", " ")
    nice_title = _clean_ws(nice_title)

    external_id = _guess_external_id(first_label)

    # We'll iterate through all attachments to find the best metadata.
    posted_date_dt_final: Optional[datetime] = None
    due_date_dt_final: Optional[datetime] = None
    description_text_final = ""
    due_text_raw_final: Optional[str] = None
    core_pdf_url_final = first_url  # fallback

    for att in attachments:
        url = att["url"]
        if not url.lower().endswith(".pdf"):
            # skip non-pdf for metadata scraping
            continue

        try:
            pdf_resp = requests.get(url, timeout=30)
        except requests.RequestException:
            continue

        if pdf_resp.status_code != 200:
            continue

        posted_dt, due_dt, desc_txt, due_text_raw = _extract_meta_plus_due(pdf_resp.content)

        # Always grab posted_date if we don't already have one
        if posted_date_dt_final is None and posted_dt is not None:
            posted_date_dt_final = posted_dt

        # Prefer a parsed datetime due_date_dt if available
        if due_date_dt_final is None and due_dt is not None:
            due_date_dt_final = due_dt
            due_text_raw_final = due_text_raw  # keep human string too
            core_pdf_url_final = url
            if desc_txt:
                description_text_final = desc_txt

        # If we *still* don't have a due_date_dt_final, but we got a human line
        # like "Due Date: November 3, 2025 5PM", grab that as well (even if we can't parse time).
        if due_date_dt_final is None and due_text_raw_final is None and due_text_raw:
            due_text_raw_final = due_text_raw
            core_pdf_url_final = url
            if desc_txt:
                description_text_final = desc_txt

        # Also grab some description if we haven't yet
        if not description_text_final and desc_txt:
            description_text_final = desc_txt

    # Fallbacks
    if posted_date_dt_final is None:
        posted_date_dt_final = datetime.utcnow()

    # Build final description string:
    extra_lines = []

    # If we have a human-readable due line, surface it
    # e.g. "Due Date: November 3, 2025 5PM"
    if due_text_raw_final:
        extra_lines.append(f"Bid Due: {due_text_raw_final}")

    # If we couldn't turn the due text into a datetime, warn to manually verify
    if due_date_dt_final is None:
        extra_lines.append(
            "⚠ Unable to convert due date/time to a specific timestamp for sorting. Please review manually."
        )

    full_description = description_text_final.strip()
    if extra_lines:
        full_description = (full_description + "\n" if full_description else "") + "\n".join(extra_lines)

    opp = RawOpportunity(
        source="metro_parks",
        source_url=core_pdf_url_final,
        title=nice_title or first_label,
        summary="",
        description=full_description.strip(),
        category="RFP",
        agency_name=AGENCY_NAME,
        location_geo="Columbus, OH",
        posted_date=posted_date_dt_final,
        due_date=due_date_dt_final,  # this stays None if we couldn't parse to datetime
        prebid_date=None,
        attachments=attachments,
        status="open",
        hash_body=None,
        external_id=external_id,
        keyword_tag="",
        date_added=datetime.now(timezone.utc),  # 👈 NEW LINE
    )

    opportunities.append(opp)
    return opportunities
