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

# Limit concurrent requests to avoid overwhelming the server
MAX_CONCURRENT_REQUESTS = 10

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


async def _fetch(session: aiohttp.ClientSession, url: str, max_retries: int = 3) -> str:
    """Fetch with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            resp = await session.get(url, timeout=timeout)
            resp.raise_for_status()
            return await _read_text_with_fallback(resp)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(f"Retry {attempt + 1}/{max_retries} for {url} after {wait_time}s: {e}")
            await asyncio.sleep(wait_time)


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
    Convert '10/29/2025' or '1/5/2025' -> datetime object
    Handles both MM/DD/YYYY and M/D/YYYY formats
    """
    text = (date_str or "").strip()
    if not text:
        return None

    # Try MM/DD/YYYY first
    try:
        return datetime.strptime(text, "%m/%d/%Y")
    except ValueError:
        pass

    # Try M/D/YYYY (no leading zeros)
    try:
        parts = text.split("/")
        if len(parts) == 3:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime(year, month, day)
    except (ValueError, IndexError):
        pass

    logger.warning(f"Could not parse date: {text}")
    return None


def _parse_opening_datetime(text: str) -> Optional[datetime]:
    """
    Parse opening date/time from detail page.
    Example: "01/09/2026 at 2:00 PM" -> datetime(2026, 1, 9, 14, 0)
    Also handles: "01/09/2026 at 2:00PM" (no space before AM/PM)
    """
    text = (text or "").strip()
    if not text:
        return None

    # Pattern: "MM/DD/YYYY at H:MM PM" or "M/D/YYYY at H:MM AM"
    # Try with space before AM/PM
    for fmt in ["%m/%d/%Y at %I:%M %p", "%m/%d/%Y at %I:%M%p"]:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    # Try without leading zeros in date
    # Example: "1/9/2026 at 2:00 PM"
    match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)', text, re.I)
    if match:
        month, day, year, hour, minute, ampm = match.groups()
        hour = int(hour)
        if ampm.upper() == 'PM' and hour != 12:
            hour += 12
        elif ampm.upper() == 'AM' and hour == 12:
            hour = 0
        try:
            return datetime(int(year), int(month), int(day), hour, int(minute))
        except ValueError:
            pass

    logger.warning(f"Could not parse opening datetime: {text}")
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
) -> Tuple[str, List[str], bool, Optional[datetime]]:
    """
    Fetch the bid detail page and pull:
    - cleaned description / scope
    - attachments
    - whether login is required for documents
    - opening date/time (more precise than listing table)

    Returns: (description, attachment_urls, requires_login, opening_datetime)
    """
    try:
        html = await _fetch(session, url)
    except Exception as e:
        logger.warning(f"Franklin County detail fetch failed {url}: {e}")
        return ("", [], False, None)

    soup = BeautifulSoup(html, "html.parser")

    # Check for login indicators
    requires_login = bool(
        soup.find(string=re.compile(r'(login|sign in|register to view)', re.I)) or
        soup.find("a", href=re.compile(r'login|signin', re.I))
    )

    description_text = _extract_clean_description(soup)

    # Extract opening date/time from detail page
    # Look for pattern like "Opening Date: 01/09/2026 at 2:00 PM"
    opening_datetime = None
    page_text = soup.get_text()
    opening_match = re.search(r'Opening Date:\s*([0-9/]+\s+at\s+[0-9:]+\s*[AP]M)', page_text, re.I)
    if opening_match:
        opening_datetime = _parse_opening_datetime(opening_match.group(1))

    attachment_urls: List[str] = []
    # Only extract attachments if no login required
    if not requires_login:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            lower = href.lower()
            if any(
                lower.endswith(ext)
                for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".ppt", ".pptx"]
            ):
                attachment_urls.append(_abs_url(href))
    else:
        logger.info(f"Documents require login for {url}")

    return (description_text, attachment_urls, requires_login, opening_datetime)


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

            # Check for closed/awarded status in the row
            row_text = tr.get_text(" ", strip=True).lower()
            is_closed = any(word in row_text for word in ["closed", "awarded", "cancelled"])

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
                    "is_closed": is_closed,
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

    logger.info(f"Franklin County: fetching details for {len(rows)} opportunities...")

    # Fetch all detail pages in parallel with rate limiting
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def fetch_with_limit(session: aiohttp.ClientSession, url: str):
        async with semaphore:
            return await _fetch_detail_description_and_attachments(session, url)

    async with aiohttp.ClientSession() as session:
        detail_tasks = [
            fetch_with_limit(session, row["detail_url"])
            for row in rows
        ]
        detail_results = await asyncio.gather(*detail_tasks, return_exceptions=True)

    # Count successful fetches for logging
    successful_fetches = len([r for r in detail_results if not isinstance(r, Exception)])
    logger.info(f"Franklin County: fetched details for {successful_fetches}/{len(rows)} opportunities")

    out: List[RawOpportunity] = []

    for row, detail_result in zip(rows, detail_results):
        # Handle exceptions from gather
        if isinstance(detail_result, Exception):
            logger.warning(f"Detail fetch failed for {row['detail_url']}: {detail_result}")
            detail_desc, attachment_urls, requires_login, opening_datetime = "", [], False, None
        else:
            detail_desc, attachment_urls, requires_login, opening_datetime = detail_result

        contact_bits = []
        if row["contact_name"]:
            contact_bits.append(f"Contact: {row['contact_name']}")
        if row["contact_email"]:
            contact_bits.append(f"Email: {row['contact_email']}")
        contact_summary = " | ".join(contact_bits)

        # In Franklin County's portal, "Opening Date" is when bids are DUE (submission deadline)
        # This is when they open sealed bids - submissions must be in before this time
        # Use the more precise datetime from detail page if available, otherwise fall back to listing table date
        due_dt = opening_datetime if opening_datetime else row["opening_dt"]
        posted_date = None  # We don't have the actual posting date from the listing

        trimmed_desc = (
            (detail_desc[:400] + " ...")
            if detail_desc and len(detail_desc) > 400
            else detail_desc
        )
        summary_text = trimmed_desc or ""

        # Add login notice if required
        if requires_login:
            summary_text = f"[Login required for documents] {summary_text}"

        if due_dt:
            # Show time if we have it (from detail page), otherwise just date
            if opening_datetime:
                due_str = due_dt.strftime('%m/%d/%Y at %I:%M %p')
            else:
                due_str = due_dt.strftime('%m/%d/%Y')
            summary_text = f"{summary_text} (Due: {due_str})"
        if contact_summary:
            summary_text = (summary_text + " " + contact_summary).strip()

        category_guess = _tag_category(
            title=row["title"],
            desc=detail_desc,
        )

        # 👇 normalize the "RFP# …" cell to just "2025-46-19"
        clean_ref = _normalize_ref_no(row["ref_no"])

        # Determine status
        # Mark as closed if:
        # 1. Row explicitly says closed/awarded/cancelled OR
        # 2. Due date is in the past
        # Note: Use timezone-naive datetime.now() since parsed dates are also timezone-naive
        is_past_due = due_dt and due_dt < datetime.now()
        status = "closed" if (row["is_closed"] or is_past_due) else "open"

        out.append(
            RawOpportunity(
                agency_name=AGENCY_NAME,
                title=row["title"],
                summary=summary_text.strip(),
                description=detail_desc,
                due_date=due_dt,
                posted_date=posted_date,
                prebid_date=None,
                source=row["detail_url"],
                source_url=row["detail_url"],
                category=category_guess,
                location_geo=None,
                attachments=attachment_urls,
                status=status,
                external_id=clean_ref,  # ✅ now the opportunities table gets 2025-46-19
                date_added=datetime.now(timezone.utc),
            )
        )

    open_count = len([o for o in out if o.status == 'open'])
    closed_count = len([o for o in out if o.status == 'closed'])
    logger.info(f"Franklin County: scraped {len(out)} row(s) ({open_count} open, {closed_count} closed).")
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