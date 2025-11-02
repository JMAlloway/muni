import re
import requests
from bs4 import BeautifulSoup, Tag
from datetime import datetime
from typing import List, Optional

from app.ingest.base import RawOpportunity

AGENCY_NAME = "Columbus Metropolitan Library"
BASE_URL = "https://www.columbuslibrary.org/doing-business/"

# --- Regex patterns we might still fall back to ---
DATE_PATTERNS = [
    r"Issue Date:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
    r"Issue Date:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
    r"Issued:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
]

DUE_PATTERNS = [
    r"Deadline for Submittal:\s*(.+?)(?:\r?\n)",
    r"Proposals?\s+must\s+be\s+received\s+no\s+later\s+than\s*(.+?)(?:\r?\n)",
    r"Bids?\s+must\s+be\s+received\s+no\s+later\s+than\s*(.+?)(?:\r?\n)",
    r"must\s+be\s+received\s+no\s+later\s+than\s*(.+?)(?:\r?\n)",
    r"(?:Proposal|Bid)\s+Due\s*[:\-]?\s*(.+?)(?:\r?\n)",
    r"Due Date\s*[:\-]?\s*(.+?)(?:\r?\n)",
]

OVERVIEW_PATTERN = r"\b(OVERVIEW|INTRODUCTION|PROJECT SCOPE)\b(.{0,1200})"


def _clean_ws(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _extract_date_only(text: str) -> Optional[str]:
    """
    Given a line like:
      "November 18, 2025"
      "November 18, 2025 No later than 12:00 Noon"
      "10/22/2025 12:00 PM"
    return just the date-ish part we can feed to _normalize_date().
    """
    # Month dd, yyyy
    m_long = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", text)
    if m_long:
        return m_long.group(1)

    # mm/dd/yyyy
    m_short = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
    if m_short:
        return m_short.group(1)

    # fall back
    return text.strip()


def _normalize_date(raw: Optional[str]) -> Optional[datetime]:
    """
    Turn a cleaned date string like "November 18, 2025" or "10/21/2025"
    into datetime. If we can't parse, return None.
    """
    if not raw:
        return None

    raw = raw.replace("No later than", "")
    raw = raw.replace("no later than", "")
    raw = raw.replace("No Later Than", "")
    raw = raw.replace("COLUMBUS, OHIO", "")
    raw = raw.replace("ET", "").replace("EST", "").replace("EDT", "")
    raw = _clean_ws(raw)

    fmts = [
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M",
        "%B %d, %Y",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M",
        "%m/%d/%Y",
    ]

    for f in fmts:
        try:
            return datetime.strptime(raw, f)
        except ValueError:
            continue
    return None


def _extract_meta_from_pdf_bytes(pdf_bytes: bytes):
    """
    Extract posted_date_dt, due_date_dt, description_text from PDF.
    NOTE: This ONLY works if the PDF has an embedded text layer.
          If it's a scanned image (CML often is), due_date_dt will be None.
    """
    try:
        txt = pdf_bytes.decode("utf-8", errors="ignore")
    except Exception:
        txt = pdf_bytes.decode("latin-1", errors="ignore")

    lines = [l.strip() for l in txt.splitlines()]

    posted_date_dt: Optional[datetime] = None
    due_date_dt: Optional[datetime] = None

    # Line-based scan first (preferred)
    for idx, line in enumerate(lines):
        low = line.lower()

        # Posted / Issue Date handling
        if "issue date" in low or "issued:" in low:
            m_same = re.search(r"(issue date|issued)\s*:\s*(.+)$", line, flags=re.IGNORECASE)
            if m_same:
                date_only = _extract_date_only(m_same.group(2))
                maybe_posted = _normalize_date(date_only)
                if maybe_posted:
                    posted_date_dt = maybe_posted
            else:
                # look ahead a few lines
                for look_ahead in range(1, 4):
                    if idx + look_ahead < len(lines):
                        nxt_line = lines[idx + look_ahead].strip()
                        if nxt_line:
                            date_only = _extract_date_only(nxt_line)
                            maybe_posted = _normalize_date(date_only)
                            if maybe_posted:
                                posted_date_dt = maybe_posted
                                break

        # Due date handling ("Deadline for Submittal", etc.)
        if (
            "deadline for submittal" in low
            or "proposal due" in low
            or "bid due" in low
            or "due date" in low
        ):
            m_same = re.search(
                r"(deadline for submittal|proposal due|bid due|due date)\s*:\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if m_same:
                date_only = _extract_date_only(m_same.group(2))
                maybe_due = _normalize_date(date_only)
                if maybe_due:
                    due_date_dt = maybe_due
            if due_date_dt is None:
                # look ahead a few lines
                for look_ahead in range(1, 4):
                    if idx + look_ahead < len(lines):
                        nxt_line = lines[idx + look_ahead].strip()
                        if nxt_line:
                            date_only = _extract_date_only(nxt_line)
                            maybe_due = _normalize_date(date_only)
                            if maybe_due:
                                due_date_dt = maybe_due
                                break

    # Regex fallback if line-based missed:
    if posted_date_dt is None:
        for pat in DATE_PATTERNS:
            m = re.search(pat, txt, flags=re.IGNORECASE)
            if m:
                date_only = _extract_date_only(m.group(1))
                maybe_posted = _normalize_date(date_only)
                if maybe_posted:
                    posted_date_dt = maybe_posted
                    break

    if due_date_dt is None:
        for pat in DUE_PATTERNS:
            m = re.search(pat, txt, flags=re.IGNORECASE)
            if m:
                date_only = _extract_date_only(m.group(1))
                maybe_due = _normalize_date(date_only)
                if maybe_due:
                    due_date_dt = maybe_due
                    break

    # High-level description (best effort)
    description_text = ""
    m_desc = re.search(OVERVIEW_PATTERN, txt, flags=re.IGNORECASE | re.DOTALL)
    if m_desc:
        description_text = _clean_ws(m_desc.group(2))[:800]

    # Always set posted_date_dt so opportunity surfaces in UI
    if posted_date_dt is None:
        posted_date_dt = datetime.utcnow()

    return posted_date_dt, due_date_dt, description_text


def _parse_headline(headline: str):
    """
    Extract:
      category        "Request for Proposal"
      solicitation_id "25-020"
      title           "Intrusion Monitoring Services"
    Works even if they don't include a dash before title.
    """
    clean = headline.replace("–", "-")
    clean = _clean_ws(clean)

    m = re.search(r"(CML\s+(\d{2}-\d{3}))", clean, flags=re.IGNORECASE)

    category = ""
    solicitation_id = ""
    title = headline.strip()

    if m:
        solicitation_id = m.group(2)  # "25-020"
        before = clean[:m.start()].strip(" -")
        after = clean[m.end():].strip(" -")
        category = before          # "Request for Proposal"
        title = after if after else headline.strip()

    return category, solicitation_id, title


def fetch() -> List[RawOpportunity]:
    """
    Scrape CML Bid Opportunities:
    - Find the "Bid Opportunities" container.
    - Walk children after that heading.
    - For each visible 'elementor-widget-text-editor' block that looks like "CML 25-020 ...",
      pair it with the following 'elementor-widget-icon-list' block for attachments.
    - Extract PDF metadata to get posted_date, due_date, description.
    - Use solicitation_id to keep source_url unique in DB.
    - If we can't read a due date (most CML PDFs are scanned),
      we tag the description so you know to enter it manually.
    """
    resp = requests.get(BASE_URL, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # locate the Bid Opportunities heading block
    bid_header = None
    for h in soup.find_all(["h1", "h2", "h3", "h4", "div", "span", "p", "strong", "b"]):
        text_clean = _clean_ws(h.get_text(" ", strip=True)).lower()
        if text_clean == "bid opportunities":
            bid_header = h
            break
    if not bid_header:
        return []

    container = bid_header.parent
    children = list(container.children)

    try:
        start_idx = children.index(bid_header) + 1
    except ValueError:
        return []

    opportunities: List[RawOpportunity] = []

    i = start_idx
    while i < len(children):
        node = children[i]

        # stop when we hit the next section header ("Recent Solicitations and Awards", etc.)
        if isinstance(node, Tag) and node.name in ["h1", "h2", "h3", "h4"]:
            break

        if (
            isinstance(node, Tag)
            and node.name == "div"
            and "elementor-widget-text-editor" in (node.get("class") or [])
        ):
            classes = node.get("class") or []

            # skip hidden/archived stuff
            if any(c.startswith("elementor-hidden") for c in classes):
                i += 1
                continue

            headline_text = _clean_ws(node.get_text(" ", strip=True))

            # must look like a live solicitation
            if not ("cml" in headline_text.lower() and re.search(r"\d{2}-\d{3}", headline_text)):
                i += 1
                continue

            # attachments are in the *next* sibling div IF that next sibling
            # is the icon-list block. (This matches what you said "only one that pulls two")
            attachments_list = []
            if i + 1 < len(children):
                nxt = children[i + 1]
                if (
                    isinstance(nxt, Tag)
                    and nxt.name == "div"
                    and "elementor-widget-icon-list" in (nxt.get("class") or [])
                ):
                    for a in nxt.find_all("a", href=True):
                        attachments_list.append({
                            "label": _clean_ws(a.get_text(" ", strip=True)),
                            "url": a["href"],
                        })
                    i += 1  # consume that attachment block so we don't treat it as a new headline next loop

            category, solicitation_id, title = _parse_headline(headline_text)

            # pick a unique source_url so we don't overwrite 25-019 with 25-020
            if attachments_list:
                core_pdf_url = attachments_list[0]["url"]
            else:
                core_pdf_url = f"{BASE_URL}#CML-{solicitation_id or _clean_ws(headline_text)}"

            posted_date_dt = None
            due_date_dt = None
            description_text = ""

            # Try the first attachment PDF for metadata
            if core_pdf_url.lower().endswith(".pdf"):
                try:
                    pdf_resp = requests.get(core_pdf_url, timeout=30)
                    if pdf_resp.status_code == 200:
                        posted_date_dt, due_date_dt, desc_from_pdf = _extract_meta_from_pdf_bytes(
                            pdf_resp.content
                        )
                        if desc_from_pdf:
                            description_text = desc_from_pdf
                except requests.RequestException:
                    pass
            else:
                # no pdf? give posted_date so table still sorts
                posted_date_dt = datetime.utcnow()

            # If due_date_dt is still None (likely scanned PDF),
            # drop a manual-review note into description so you catch it in admin.
            if due_date_dt is None:
                manual_flag = (
                    "⚠ Unable to auto-read due date from PDF. "
                    "Please review and enter deadline manually."
                )
                if description_text:
                    description_text = f"{description_text}\n\n{manual_flag}"
                else:
                    description_text = manual_flag

            opp = RawOpportunity(
                source="columbus_metropolitan_library",
                source_url=core_pdf_url,
                title=title or headline_text,
                summary="",
                description=description_text,
                category=category or "",
                agency_name=AGENCY_NAME,
                location_geo="Columbus, OH",
                posted_date=posted_date_dt,
                due_date=due_date_dt,  # None means your UI will show TBD
                prebid_date=None,
                attachments=attachments_list,
                status="open",
                hash_body=None,
                external_id=solicitation_id or "",
                keyword_tag="",
            )

            opportunities.append(opp)

        i += 1

    return opportunities
