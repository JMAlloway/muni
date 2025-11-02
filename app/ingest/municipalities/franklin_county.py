import asyncio
import logging
import re
from typing import List, Optional, Tuple
from datetime import datetime, timezone

import aiohttp
from bs4 import BeautifulSoup

from app.ingest.base import RawOpportunity

logger = logging.getLogger(__name__)

AGENCY_NAME = "Franklin County, Ohio"
BASE_URL = "https://bids.franklincountyohio.gov"
LIST_URL = BASE_URL + "/"  # public listing table


# ---------------------------------
# HTTP helpers
# ---------------------------------

def _normalize_ref_no(ref_no: str) -> str:
    """
    Turn things like:
      "RFP# 2025-46-19"
      "RFQ#2025-10"
      "Bid # 25-003"
    into just:
      "2025-46-19"
      "2025-10"
      "25-003"
    """
    if not ref_no:
        return ""

    txt = ref_no.strip()
    # drop leading label like RFP / RFQ / BID / ITB, with optional # and spaces
    txt = re.sub(r"^(rfp|rfq|itb|bid)\s*#?\s*", "", txt, flags=re.IGNORECASE)
    return txt.strip()

async def _read_text_with_fallback(resp: aiohttp.ClientResponse) -> str:
    """
    Robust decode for legacy encodings.
    """
    raw = await resp.read()

    if resp.charset:
        try:
            return raw.decode(resp.charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            pass

    try:
        return raw.decode("cp1252", errors="replace")
    except UnicodeDecodeError:
        pass

    return raw.decode("latin-1", errors="replace")


async def _fetch(session: aiohttp.ClientSession, url: str) -> str:
    resp = await session.get(url)
    resp.raise_for_status()
    return await _read_text_with_fallback(resp)


async def _fetch_html(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        return await _fetch(session, url)


def _abs_url(href: str) -> str:
    """
    Convert relative links like 'bids.cfm?id=8875' into absolute URLs.
    """
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href.lstrip("/")


def _parse_mmddyyyy(date_str: str) -> Optional[datetime]:
    """
    Convert '10/29/2025' -> datetime(2025-10-29 00:00:00)
    """
    text = (date_str or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%m/%d/%Y")
    except ValueError:
        return None


# ---------------------------------
# Category tagging
# ---------------------------------

def _tag_category(title: str, desc: str) -> str:
    """
    Heuristic classification by keywords in title/description.
    We'll normalize to lowercase and check for buckets.
    """

    blob = f"{title} {desc}".lower()

    construction_keywords = [
        "engineering services",
        "professional engineering",
        "design services",
        "construction",
        "bridge",
        "paving",
        "asphalt",
        "relocation services",
        "lease and relocation",  # still facilities/real estate style capital work
        "rfq",  # county often uses RFQ for A/E
    ]

    it_keywords = [
        "software",
        "platform",
        "data",
        "network",
        "cloud",
        "system",
        "ehr",
        "pharmacy benefits manager",  # PBM is technically benefits admin but it's strongly systems/admin
        "benefits manager",
        "identity theft",
        "employee assistance program",
        "eap",
    ]

    fleet_keywords = [
        "vehicle",
        "vehicles",
        "towing",
        "impound",
        "fleet",
        "squad robot",
        "robot",  # bomb squad robot is definitely equipment procurement
        "service vehicles",
    ]

    animal_keywords = [
        "spay",
        "neuter",
        "veterinary",
        "veterinary care",
        "animal",
        "after-hours emergency veterinary",
    ]

    health_keywords = [
        "behavioral health",
        "mental health",
        "health services",
        "medical",
        "drug & alcohol testing",
        "drug and alcohol testing",
        "pharmacy benefits",
        "pet insurance",
    ]

    # Check in priority order. Some will overlap; we'll return the first matching bucket.
    for kw in construction_keywords:
        if kw in blob:
            return "Construction / Facilities / Engineering"

    for kw in it_keywords:
        if kw in blob:
            return "IT / Systems / Benefits Admin"

    for kw in fleet_keywords:
        if kw in blob:
            return "Vehicles / Fleet / Equipment"

    for kw in animal_keywords:
        if kw in blob:
            return "Animal / Veterinary Services"

    for kw in health_keywords:
        if kw in blob:
            return "Healthcare / Wellness / HR Benefits"

    # Default catch-all
    return "Professional / Other Services"


# ---------------------------------
# Detail page parsing
# ---------------------------------

def _extract_clean_description(soup: BeautifulSoup) -> str:
    """
    Try to pull a human-usable scope/description instead of dumping the whole page.
    Strategy:
    1. Look for <p> blocks that look like description/scope language.
    2. Fall back to the single longest <p>.
    3. If no <p>, fall back to page-wide text.
    """

    paras = soup.find_all("p")
    best_candidate = ""
    best_len = 0

    # Keywords that suggest actual scope language
    interesting_words = [
        "description",
        "scope",
        "services",
        "purpose",
        "intent",
        "the county is seeking",
        "the county is requesting",
        "the county intends",
    ]

    for p in paras:
        txt = p.get_text(" ", strip=True)
        if not txt:
            continue
        normalized = txt.lower()

        # Heuristic boost if it sounds like scope text
        boost = 0
        for w in interesting_words:
            if w in normalized:
                boost += 50

        length_score = len(txt) + boost

        if length_score > best_len:
            best_len = length_score
            best_candidate = txt

    if best_candidate:
        return " ".join(best_candidate.split())

    # fallback: just grab longest <p>
    for p in paras:
        txt = p.get_text(" ", strip=True)
        if len(txt) > best_len:
            best_len = len(txt)
            best_candidate = txt

    if best_candidate:
        return " ".join(best_candidate.split())

    # ultimate fallback: entire page text
    page_text = soup.get_text(" ", strip=True)
    return " ".join(page_text.split())


async def _fetch_detail_description_and_attachments(
    session: aiohttp.ClientSession,
    url: str
) -> Tuple[str, List[str]]:
    """
    Fetch the bid detail page and pull:
    - cleaned description / scope
    - attachments
    """
    try:
        html = await _fetch(session, url)
    except Exception as e:
        logger.warning(f"Franklin County detail fetch failed {url}: {e}")
        return ("", [])

    soup = BeautifulSoup(html, "html.parser")

    description_text = _extract_clean_description(soup)

    attachment_urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lower = href.lower()
        if any(
            lower.endswith(ext)
            for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".ppt", ".pptx"]
        ):
            attachment_urls.append(_abs_url(href))

    return (description_text, attachment_urls)


# ---------------------------------
# Listing page parsing
# ---------------------------------

def _extract_rows_from_table(soup: BeautifulSoup) -> List[dict]:
    """
    Parse each <tr> that has data cells.
    """
    out: List[dict] = []

    # Find the table you showed: class="sticky sortable table table-striped mobile"
    # We'll key off the 'sticky' class first, fallback to all tables if not present.
    tables = soup.find_all("table", class_="sticky")
    if not tables:
        tables = soup.find_all("table")

    for table in tables:
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            # Skip header & malformed rows
            if len(tds) < 4:
                continue

            # Column 0: RFP / RFQ ref no
            ref_no = tds[0].get_text(" ", strip=True)

            # Column 1: title + detail link
            link_tag = tds[1].find("a", href=True)
            if not link_tag:
                continue
            title_text = link_tag.get_text(" ", strip=True)
            detail_url = _abs_url(link_tag["href"])

            # Column 2: Opening Date
            opening_text = tds[2].get_text(" ", strip=True)
            opening_dt = _parse_mmddyyyy(opening_text)

            # Column 3: Contact name + email
            contact_name = ""
            contact_email = ""
            contact_a = tds[3].find("a", href=True)
            if contact_a:
                contact_name = contact_a.get_text(" ", strip=True)
                href_val = contact_a["href"]
                if href_val.lower().startswith("mailto:"):
                    contact_email = href_val[len("mailto:"):].strip()

            out.append(
                {
                    "ref_no": ref_no,
                    "title": title_text,
                    "detail_url": detail_url,
                    "opening_dt": opening_dt,
                    "contact_name": contact_name,
                    "contact_email": contact_email,
                }
            )

    return out


# ---------------------------------
# Main scrape
# ---------------------------------

async def _scrape_listing_page() -> List[RawOpportunity]:
    listing_html = await _fetch_html(LIST_URL)
    soup = BeautifulSoup(listing_html, "html.parser")

    rows = _extract_rows_from_table(soup)
    if not rows:
        logger.info("Franklin County: no bid rows parsed after table scan.")
        return []

    out: List[RawOpportunity] = []

    async with aiohttp.ClientSession() as session:
        for row in rows:
            # fetch detail page for each row
            detail_desc, attachment_urls = await _fetch_detail_description_and_attachments(
                session,
                row["detail_url"],
            )

            contact_bits = []
            if row["contact_name"]:
                contact_bits.append(f"Contact: {row['contact_name']}")
            if row["contact_email"]:
                contact_bits.append(f"Email: {row['contact_email']}")
            contact_summary = " | ".join(contact_bits)

            opening_dt = row["opening_dt"]
            due_dt = None  # Franklin County shows Opening, not vendor due

            trimmed_desc = (
                (detail_desc[:400] + " ...")
                if detail_desc and len(detail_desc) > 400
                else detail_desc
            )
            summary_text = trimmed_desc or ""
            if opening_dt:
                summary_text = f"{summary_text} (Opening: {opening_dt.strftime('%m/%d/%Y')})"
            if contact_summary:
                summary_text = (summary_text + " " + contact_summary).strip()

            category_guess = _tag_category(
                title=row["title"],
                desc=detail_desc,
            )

            # 👇 normalize the “RFP# …” cell to just “2025-46-19”
            clean_ref = _normalize_ref_no(row["ref_no"])

            out.append(
                RawOpportunity(
                    agency_name=AGENCY_NAME,
                    title=row["title"],
                    summary=summary_text.strip(),
                    description=detail_desc,
                    due_date=due_dt,
                    posted_date=opening_dt,
                    prebid_date=None,
                    source=row["detail_url"],
                    source_url=row["detail_url"],
                    category=category_guess,
                    location_geo=None,
                    attachments=attachment_urls,
                    status="open",
                    external_id=clean_ref,  # ✅ now the opportunities table gets 2025-46-19
                    date_added=datetime.now(timezone.utc),
                )
            )

    logger.info(f"Franklin County: scraped {len(out)} row(s).")
    return out


# ---------------------------------
# Public entrypoints
# ---------------------------------

async def get_opportunities() -> List[RawOpportunity]:
    return await _scrape_listing_page()


async def fetch() -> List[RawOpportunity]:
    return await get_opportunities()


# ---------------------------------
# Local debug runner
# ---------------------------------

if __name__ == "__main__":
    async def _test():
        opps = await get_opportunities()
        for o in opps:
            print("-----")
            print("title:", o.title)
            print("category:", o.category)
            print("due:", o.due_date)
            print("url:", o.source_url)
            print("summary:", (o.summary or "")[:240], "...")
            print("attachments:", o.attachments)
            print()

    asyncio.run(_test())
