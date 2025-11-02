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

AGENCY_NAME = "Mid-Ohio Regional Planning Commission (MORPC)"
BASE_URL = "https://www.morpc.org"
BIDDING_URL = f"{BASE_URL}/rfps-rfqs/"

DATE_PATTERNS = [
    r"([A-Za-z]+ \d{1,2}, \d{4})\s+(\d{1,2}:\d{2}\s*(?:A\.?M\.?|P\.?M\.?))",
    r"([A-Za-z]+ \d{1,2}, \d{4}).{0,5}(\d{1,2}:\d{2}\s*(?:A\.?M\.?|P\.?M\.?))",
    r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2}\s*(?:A\.?M\.?|P\.?M\.?))",
]

MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def _parse_due_datetime(hint: str) -> Optional[datetime]:
    text = hint.strip()
    for pat in DATE_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        date_part = m.group(1).strip()
        time_part = m.group(2).strip()

        time_norm = time_part.replace(".", "").upper()  # "5:00 PM"

        # ex: November 6, 2025
        m_long = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", date_part)
        if m_long:
            month_name = m_long.group(1).upper()
            day = int(m_long.group(2))
            year = int(m_long.group(3))
            month_num = MONTHS.get(month_name)
            if not month_num:
                return None
            try:
                return datetime.strptime(
                    f"{year:04d}-{month_num:02d}-{day:02d} {time_norm}",
                    "%Y-%m-%d %I:%M %p",
                )
            except ValueError:
                return None

        # ex: 11/06/2025
        m_short = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_part)
        if m_short:
            month_num = int(m_short.group(1))
            day = int(m_short.group(2))
            year = int(m_short.group(3))
            try:
                return datetime.strptime(
                    f"{year:04d}-{month_num:02d}-{day:02d} {time_norm}",
                    "%Y-%m-%d %I:%M %p",
                )
            except ValueError:
                return None

    return None


def _safe_abs_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def _safe_get_pdf(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content:
            return r.content
    except requests.RequestException:
        return None
    return None


def _guess_external_id(text: str) -> str:
    t = text.upper()
    m = re.search(r"\b(RFP|RFQ)[^\s:]*", t)
    if m:
        return m.group(0)
    m2 = re.search(r"\b20\d{2}[-/ ]?\d{2,3}\b", t)
    if m2:
        return m2.group(0)
    return ""


def _find_due_hint_near_link(a_tag) -> Optional[str]:
    parent = a_tag.parent
    if parent:
        parent_text = _clean_ws(parent.get_text(" ", strip=True))
        if ("due" in parent_text.lower() or "deadline" in parent_text.lower()) and len(parent_text) > 5:
            return parent_text

    sib = parent.next_sibling if parent else None
    while sib and hasattr(sib, "get_text"):
        sib_text = _clean_ws(sib.get_text(" ", strip=True))
        low = sib_text.lower()
        if ("due" in low or "deadline" in low) and len(sib_text) > 5:
            return sib_text
        sib = sib.next_sibling

    sib2 = a_tag.next_sibling
    while sib2 and hasattr(sib2, "get_text"):
        sib2_text = _clean_ws(sib2.get_text(" ", strip=True))
        low2 = sib2_text.lower()
        if ("due" in low2 or "deadline" in low2) and len(sib2_text) > 5:
            return sib2_text
        sib2 = sib2.next_sibling

    return None


def _find_title_near_link(a_tag, link_text: str) -> str:
    """
    If the <a> text is just "RFP:" or "RFQ:" etc., try to grab a better title
    from a sibling paragraph/list item immediately after.
    """
    bare = link_text.strip().rstrip("-:").upper()
    if bare not in ("RFP", "RFQ"):
        # looks fine already
        return link_text

    # try sibling/next <p>/<li> for a descriptive phrase
    parent = a_tag.parent

    # 1. same parent, but without the anchor text
    if parent:
        # get full parent text, then remove the anchor text portion once
        parent_full = _clean_ws(parent.get_text(" ", strip=True))
        parent_full_upper = parent_full.upper()
        # if parent_full is longer than just "RFQ:" etc, use that
        if len(parent_full_upper) > len(bare) + 3:
            return f"{bare}: " + parent_full.replace(link_text, "").strip()

    # 2. parent's next siblings
    sib = parent.next_sibling if parent else None
    while sib and hasattr(sib, "get_text"):
        sib_text = _clean_ws(sib.get_text(" ", strip=True))
        if sib_text and len(sib_text) > 3:
            # Make something like "RFQ: Insulation Contractor..."
            return f"{bare}: {sib_text}"
        sib = sib.next_sibling

    # 3. <a> tag's own next siblings
    sib2 = a_tag.next_sibling
    while sib2 and hasattr(sib2, "get_text"):
        sib2_text = _clean_ws(sib2.get_text(" ", strip=True))
        if sib2_text and len(sib2_text) > 3:
            return f"{bare}: {sib2_text}"
        sib2 = sib2.next_sibling

    # fallback to whatever we had
    return link_text


def fetch() -> List[RawOpportunity]:
    """
    Grab every PDF link on MORPC page.
    Improve:
      - derive title if <a> text is just 'RFP:'/'RFQ:'
      - capture due date hint near link and parse
      - scrape PDF for backup details
    """
    page = requests.get(BIDDING_URL, timeout=30)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")

    pdf_entries: List[Tuple[str, str, Optional[str]]] = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href.lower().endswith(".pdf"):
            continue

        pdf_url = _safe_abs_url(href)
        raw_text = _clean_ws(a.get_text(" ", strip=True)) or pdf_url
        smart_title = _find_title_near_link(a, raw_text)

        due_hint_html = _find_due_hint_near_link(a)

        pdf_entries.append((smart_title, pdf_url, due_hint_html))

    # dedupe by URL
    seen = set()
    unique_entries = []
    for title_text, pdf_url, due_hint_html in pdf_entries:
        if pdf_url in seen:
            continue
        seen.add(pdf_url)
        unique_entries.append((title_text, pdf_url, due_hint_html))

    results: List[RawOpportunity] = []

    for title_text, pdf_url, due_hint_html in unique_entries:
        posted_dt: Optional[datetime] = None
        parsed_due_dt: Optional[datetime] = None
        description_body = ""
        extra_bits = []

        # 1. due hint from HTML (what you wanted: “just use that date”)
        if due_hint_html:
            parsed_due_dt = _parse_due_datetime(due_hint_html)
            extra_bits.append(f"HTML due info: {due_hint_html}")

        # 2. pull PDF metadata as backup
        pdf_bytes = _safe_get_pdf(pdf_url)
        if pdf_bytes:
            pdf_posted_dt, pdf_due_dt, pdf_desc = _extract_meta_from_pdf_bytes(pdf_bytes)
            if pdf_desc:
                description_body = pdf_desc.strip()

            if posted_dt is None and pdf_posted_dt:
                posted_dt = pdf_posted_dt
            if parsed_due_dt is None and pdf_due_dt:
                parsed_due_dt = pdf_due_dt

        if posted_dt is None:
            posted_dt = datetime.utcnow()

        if parsed_due_dt is None:
            extra_bits.append("Due date not machine-parsed. Verify manually.")

        final_description = description_body
        if extra_bits:
            final_description = (final_description + "\n" if final_description else "") + "\n".join(extra_bits)

        opp = RawOpportunity(
            source="morpc",
            source_url=pdf_url,
            title=title_text,  # now fixed for the blank "RFQ:" case
            summary="",
            description=final_description,
            category="RFP/RFQ",
            agency_name=AGENCY_NAME,
            location_geo="Central Ohio",
            posted_date=posted_dt,
            due_date=parsed_due_dt,
            prebid_date=None,
            attachments=[{"label": title_text, "url": pdf_url}],
            status="open",
            hash_body=None,
            external_id=_guess_external_id(title_text),
            keyword_tag="",
            date_added=datetime.now(timezone.utc),  # 👈 NEW LINE
        )

        results.append(opp)

    return results
