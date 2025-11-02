import re
from urllib.parse import urljoin
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from app.ingest.base import RawOpportunity
from app.ingest.municipalities.columbus_metropolitan_library import (
    _clean_ws,
)


AGENCY_NAME = "Dublin City Schools"
BASE_URL = "https://www.dublinschools.net"
BIDDING_URL = (
    "https://www.dublinschools.net/departments/operations/bids-and-rfps"
)


def _guess_external_id(text: str) -> str:
    """
    Heuristic to produce a semi-stable external ID string.
    Same strategy you used in metro_parks: look for a year or an RFP-style token.
    """
    t = text.upper()

    # first 4-digit year like 2025, 2026, etc.
    m_year = re.search(r"\b(20\d{2})\b", t)
    if m_year:
        return m_year.group(1)

    # fallback: something like RFP-1234 etc.
    m_rfp = re.search(r"\bRFP[^\s]{0,20}", t)
    if m_rfp:
        return m_rfp.group(0)

    # last resort: slugify first ~12 chars
    slug = re.sub(r"[^A-Z0-9]+", "-", t).strip("-")
    return slug[:24]


def _normalize_due_line(raw: str) -> str:
    """
    Input example:
      'Bids due before 2pm on November 6th 2025'
    We'll clean ordinal suffixes ('6th' -> '6') and make time more parseable ('2pm' -> '2 PM').
    Returns cleaned string and we keep original for description separately.
    """
    s = _clean_ws(raw)

    # lowercase -> then upcase AM/PM cleanly
    # we'll capture e.g. '2pm', '10:30am', '2 p.m.' etc. normalize to '2 PM'
    def _fix_time(m):
        hhmm = m.group(1)
        ampm = m.group(2)
        return f"{hhmm} {ampm.upper().replace('.', '')}"

    s = re.sub(
        r"\b(\d{1,2}(?::\d{2})?)\s*([ap]\.?m\.?)\b",
        _fix_time,
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(\d{1,2}(?::\d{2})?)([ap]\.?m\.?)\b",
        _fix_time,
        s,
        flags=re.IGNORECASE,
    )

    # remove 'before' or 'by' fluff for parsing
    s = re.sub(r"\b(bids?\s+due\s+(before|by)\s+)", "Due ", s, flags=re.I)
    s = re.sub(r"\b(bids?\s+due\s+on\s+)", "Due ", s, flags=re.I)
    s = re.sub(r"\bon\s+(?=[A-Za-z]+\s+\d{1,2})", "", s, flags=re.I)

    # strip ordinal suffixes: 1st/2nd/3rd/4th -> 1/2/3/4
    s = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", s, flags=re.I)

    return _clean_ws(s)


def _parse_due_datetime_from_line(due_line: str) -> Optional[datetime]:
    """
    Try to extract a concrete datetime from the cleaned due line.
    We'll look for:
      'Due 2 PM November 6 2025'
      'Due November 6 2025 2 PM'
      'Due November 6 2025'
    Assumes America/New_York local; we won't localize to tzaware here since RawOpportunity
    appears to just take naive datetimes elsewhere.
    """
    txt = _normalize_due_line(due_line)

    # Pull pieces
    # We'll try two patterns:
    #   1. time first, then date
    m1 = re.search(
        r"Due\s+(\d{1,2}(?::\d{2})?\s+[AP]M)\s+([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})",
        txt,
        flags=re.I,
    )
    #   2. date then optional time
    m2 = re.search(
        r"Due\s+([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})(?:\s+(\d{1,2}(?::\d{2})?\s+[AP]M))?",
        txt,
        flags=re.I,
    )

    month_lookup = {
        "JANUARY": 1,
        "FEBRUARY": 2,
        "MARCH": 3,
        "APRIL": 4,
        "MAY": 5,
        "JUNE": 6,
        "JULY": 7,
        "AUGUST": 8,
        "SEPTEMBER": 9,
        "OCTOBER": 10,
        "NOVEMBER": 11,
        "DECEMBER": 12,
    }

    def _parse_time_to_hm(tstr: str) -> Tuple[int, int]:
        """
        Convert '2 PM' or '10:30 AM' -> (hour24, minute)
        """
        tstr = tstr.strip().upper()
        parts = tstr.split()
        clock = parts[0]  # '2' or '10:30'
        ampm = parts[1]   # 'AM'/'PM'

        if ":" in clock:
            hh_str, mm_str = clock.split(":", 1)
        else:
            hh_str, mm_str = clock, "00"

        hh = int(hh_str)
        mm = int(mm_str)

        # 12 AM -> 00, 12 PM -> 12, etc.
        if ampm == "AM":
            if hh == 12:
                hh = 0
        else:  # PM
            if hh != 12:
                hh += 12

        return hh, mm

    try:
        if m1:
            # pattern 1: time first, then date
            time_str = m1.group(1)
            month_name = m1.group(2)
            day = int(m1.group(3))
            year = int(m1.group(4))

            month = month_lookup.get(month_name.upper())
            if not month:
                return None

            hour, minute = _parse_time_to_hm(time_str)
            return datetime(year, month, day, hour, minute)

        if m2:
            # pattern 2: date then optional time
            month_name = m2.group(1)
            day = int(m2.group(2))
            year = int(m2.group(3))
            time_str = m2.group(4)

            month = month_lookup.get(month_name.upper())
            if not month:
                return None

            if time_str:
                hour, minute = _parse_time_to_hm(time_str)
            else:
                # default to 17:00 local if no time given (arbitrary but deterministic)
                hour, minute = (17, 0)

            return datetime(year, month, day, hour, minute)

    except Exception:
        return None

    return None


def fetch() -> List[RawOpportunity]:
    resp = requests.get(BIDDING_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the main content area where the open bids live.
    # From the HTML you gave, it's under:
    # <div class="fsElement fsContainer" id="fsEl_50653"> ... plus siblings fsEl_52211, fsEl_52210 ...
    # Each project is a <section class="fsElement fsContainer" id="fsEl_XXXXX">
    main_content = soup.select_one("#fsPageContent")
    if not main_content:
        return []

    project_sections = main_content.select(
        "section.fsElement.fsContainer"
    )

    opportunities: List[RawOpportunity] = []

    for sec in project_sections:
        # Title
        title_el = sec.select_one("h2.fsElementTitle")
        if not title_el:
            continue
        raw_title = _clean_ws(title_el.get_text(" ", strip=True))

        # Header content (this has due line + attachments)
        header_content = sec.select_one(".fsElementHeaderContent")
        if not header_content:
            continue

        # First <p><strong>...</strong> is the due line
        strong_due = header_content.select_one("p > strong")
        if strong_due:
            due_human = _clean_ws(strong_due.get_text(" ", strip=True))
        else:
            due_human = ""

        # attachments: any links under header_content
        attachments = []
        for a in header_content.select("a[href]"):
            label = _clean_ws(a.get_text(" ", strip=True))
            href = a.get("href", "").strip()
            if not href:
                continue
            full_url = urljoin(BASE_URL, href)
            attachments.append(
                {
                    "label": label,
                    "url": full_url,
                }
            )

        # pick a "core" url: first attachment if present, else the bids page
        core_pdf_url_final = attachments[0]["url"] if attachments else BIDDING_URL

        # try to parse due datetime
        due_date_dt = _parse_due_datetime_from_line(due_human)

        # posted_date fallback to now (UTC) since site doesn't expose it
        posted_date_dt = datetime.utcnow()

        # external_id guess
        external_id = _guess_external_id(raw_title)

        # build description
        extra_lines = []
        if due_human:
            extra_lines.append(f"Bid Due: {due_human}")
        if due_date_dt is None:
            extra_lines.append(
                "⚠ Unable to convert due date/time to a precise timestamp automatically. Please verify manually."
            )

        # Also include a short list of attachment names
        if attachments:
            att_lines = [
                f"- {att['label']}: {att['url']}"
                for att in attachments
            ]
            extra_lines.append("Attachments:\n" + "\n".join(att_lines))

        full_description = "\n".join(extra_lines).strip()

        opp = RawOpportunity(
            source="dublin_city_schools",
            source_url=core_pdf_url_final,
            title=raw_title,
            summary="",
            description=full_description,
            category="RFP",
            agency_name=AGENCY_NAME,
            location_geo="Dublin, OH",
            posted_date=posted_date_dt,
            due_date=due_date_dt,
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
