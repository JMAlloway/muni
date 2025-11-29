"""
COTA (Central Ohio Transit Authority) Procurement Scraper - FIXED VERSION

Key fixes:
- ✅ Correct detail URL parameters (XID + PID instead of RID)
- ✅ Extract question deadline from listing page
- ✅ Handles iframe-based modal properly
- ✅ All improvements from v2.0 (monitoring, logging, etc.)

Site: https://cota.dbesystem.com/FrontEnd/proposalsearchpublic.asp
Type: DBE System portal (iframe modal for details)
Update frequency: Daily
"""

import asyncio
import logging
import re
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup

from app.ingest.base import RawOpportunity
from app.ingest.municipalities.city_columbus import _classify_keyword_tag
from app.ingest.utils import safe_source_url

# Import improvement utilities (optional)
try:
    from app.ingest.monitoring import ScraperMonitor
    HAS_MONITORING = True
except ImportError:
    HAS_MONITORING = False

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

SCRAPER_VERSION = "2.1"  # Fixed version
AGENCY_NAME = "Central Ohio Transit Authority (COTA)"
BASE_URL = "https://cota.dbesystem.com"
LIST_URL = BASE_URL + "/FrontEnd/proposalsearchpublic.asp"

# FIXED: Correct URL parameters based on actual iframe src
DETAIL_URL_TEMPLATE = BASE_URL + "/FrontEnd/ProposalSearchPublicDetail.asp?XID=1989&TN=cota&PID={PID}"

# Centralized selectors
SELECTORS = {
    "opportunity_tiles": "a.RecordTile",
    "tile_description": "div.Description",
    "tile_status": "div.Status",
    "tile_date_box": "div.DateBox",
    "tile_due_date": "div.DateDue",
    "tile_question_deadline": "div.DateQuestions",  # NEW
    "attachment_extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".ppt", ".pptx"],
}

VALID_STATUSES = {"open", "due soon"}
MAX_RETRIES = 3
RETRY_DELAYS = [0.2, 0.6, 1.4]

# =============================================================================
# HTTP Utilities
# =============================================================================

async def _read_text_with_fallback(resp: aiohttp.ClientResponse) -> str:
    """Robust text decoding for legacy encodings."""
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
    """HTTP GET with retry logic and browser headers."""
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = await session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": LIST_URL,  # NEW: Pretend we came from listing page
                },
            )
            resp.raise_for_status()

            logger.debug(f"Successfully fetched {url} (attempt {attempt + 1})")
            return await _read_text_with_fallback(resp)

        except aiohttp.ClientError as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    f"Fetch failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
        except Exception as e:
            last_exc = e
            logger.error(f"Unexpected error fetching {url}: {e}")
            break

    if last_exc:
        raise last_exc
    return ""


async def _fetch_html(url: str) -> str:
    """Fetch HTML with timeout."""
    timeout = ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        return await _fetch(session, url)


def _abs_url(href: str) -> str:
    """Convert relative URLs to absolute."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href.lstrip("/")


# =============================================================================
# Date Parsing
# =============================================================================

def _clean_date_string(raw_text: str) -> str:
    """Clean common junk from date strings."""
    text = raw_text
    text = re.sub(r"\bUS/Eastern\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bET\b", "", text, flags=re.IGNORECASE)

    # Remove prefixes
    for prefix in ["Due", "Question Deadline"]:
        if text.strip().lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    return text.strip()


def _parse_datetime(raw_text: str) -> Optional[datetime]:
    """Parse date/time with Eastern timezone awareness."""
    cleaned = " ".join(raw_text.split())
    if not cleaned:
        return None

    formats = [
        "%m/%d/%Y %I:%M %p",   # 12/1/2025 2:00 pm
        "%m/%d/%Y %H:%M %p",   # 12/1/2025 14:00 pm
        "%m/%d/%Y %I:%M%p",    # 12/1/2025 2:00pm
        "%m/%d/%Y",            # 12/1/2025
    ]

    for fmt in formats:
        try:
            dt_naive = datetime.strptime(cleaned, fmt)
            dt_local = dt_naive.replace(tzinfo=ZoneInfo("America/New_York"))
            return dt_local.astimezone(timezone.utc)
        except ValueError:
            continue

    logger.debug(f"Failed to parse date: '{raw_text}'")
    return None


# =============================================================================
# Detail Page Parsing
# =============================================================================

def _extract_detail_description_dates_attachments(
    soup: BeautifulSoup,
) -> Tuple[str, Optional[datetime], Optional[datetime], List[str]]:
    """Extract details from opportunity detail page."""
    page_text = soup.get_text(" ", strip=True)
    description_text = " ".join(page_text.split())

    posted_date = None
    due_date = None
    prebid_date = None

    # Scan table rows for dates
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        label = cells[0].get_text(" ", strip=True).lower()
        value_text = cells[1].get_text(" ", strip=True)

        if any(key in label for key in ["closing", "due", "proposal due", "deadline"]):
            due_candidate = _parse_datetime(_clean_date_string(value_text))
            if due_candidate:
                due_date = due_candidate

        if any(key in label for key in ["post", "publish", "issued", "release"]):
            posted_candidate = _parse_datetime(value_text)
            if posted_candidate:
                posted_date = posted_candidate

        if "pre" in label and "bid" in label:
            prebid_candidate = _parse_datetime(_clean_date_string(value_text))
            if prebid_candidate:
                prebid_date = prebid_candidate

    # Extract attachments
    attachment_urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lower = href.lower()

        if any(lower.endswith(ext) for ext in SELECTORS["attachment_extensions"]):
            url = _abs_url(href)
            if url not in attachment_urls:
                attachment_urls.append(url)

    # Add pre-bid info to description
    if prebid_date and "pre-bid" not in description_text.lower():
        try:
            local_hint = prebid_date.astimezone(ZoneInfo("America/New_York")).strftime("%m/%d/%Y %I:%M %p")
            description_text = f"{description_text} Pre-bid meeting: {local_hint}".strip()
        except Exception:
            pass

    return (description_text, posted_date, due_date, attachment_urls)


async def _fetch_detail_opportunity(
    session: aiohttp.ClientSession,
    detail_url: str
) -> Tuple[str, Optional[datetime], Optional[datetime], List[str]]:
    """Fetch and parse opportunity detail page."""
    try:
        html = await _fetch(session, detail_url)
        soup = BeautifulSoup(html, "html.parser")
        return _extract_detail_description_dates_attachments(soup)
    except Exception as e:
        logger.warning(f"COTA detail fetch failed for {detail_url}: {e}")
        return ("", None, None, [])


# =============================================================================
# Listing Page Parsing
# =============================================================================

def _locate_opportunity_tiles(soup: BeautifulSoup) -> List[dict]:
    """
    Find opportunity tiles and extract basic info including question deadline.

    Returns:
        List of dicts with: record_id, title, due_text, question_deadline_text, status
    """
    results: List[dict] = []

    tiles = soup.find_all("a", class_="RecordTile")

    if not tiles:
        logger.debug("RecordTile class not found, using fallback selector")
        tiles = [a for a in soup.find_all("a", href=True) if "ViewDetail(" in a.get("href", "")]

    logger.info(f"Found {len(tiles)} potential opportunity tiles")

    for tile in tiles:
        # Extract PID from JavaScript: ViewDetail('344EF83E...')
        href_val = tile.get("href", "")
        match = re.search(r"ViewDetail\('([^']+)'\)", href_val)
        record_id = match.group(1).strip() if match else None

        if not record_id:
            logger.debug(f"Skipping tile without record_id: {href_val}")
            continue

        # Find description container
        desc_div = tile.find("div", class_="Description")
        if not desc_div:
            parent = tile.find_parent()
            if parent:
                desc_div = parent.find("div", class_="Description")

        if not desc_div:
            logger.debug(f"Skipping tile {record_id}: no Description div found")
            continue

        # Extract status
        status_div = desc_div.find("div", class_="Status")
        status_text = status_div.get_text(" ", strip=True) if status_div else ""
        status_clean = status_text.strip().lower()

        # Filter by status
        if status_clean not in VALID_STATUSES:
            logger.debug(f"Skipping tile {record_id}: status '{status_clean}' not in {VALID_STATUSES}")
            continue

        # Extract due date
        due_div = desc_div.find("div", class_="DateDue")
        due_div_text = due_div.get_text(" ", strip=True) if due_div else ""

        # NEW: Extract question deadline
        question_div = desc_div.find("div", class_="DateQuestions")
        question_deadline_text = question_div.get_text(" ", strip=True) if question_div else ""

        # Extract title (remove date boxes and status)
        raw_full_desc_text = desc_div.get_text(" ", strip=True)

        date_box = desc_div.find("div", class_="DateBox")
        if date_box:
            date_box_text = date_box.get_text(" ", strip=True)
            raw_full_desc_text = raw_full_desc_text.replace(date_box_text, "")

        if status_text:
            raw_full_desc_text = raw_full_desc_text.replace(status_text, "")

        title_text = " ".join(raw_full_desc_text.split())

        results.append({
            "record_id": record_id,
            "title": title_text,
            "due_text": due_div_text,
            "question_deadline_text": question_deadline_text,  # NEW
            "status": status_text,
        })

    logger.info(f"Filtered to {len(results)} valid opportunities")
    return results


# =============================================================================
# Main Scraper
# =============================================================================

async def _scrape_listing_page() -> List[RawOpportunity]:
    """Main scraping function."""
    logger.info(f"Starting COTA scraper v{SCRAPER_VERSION}")

    listing_html = await _fetch_html(LIST_URL)
    soup = BeautifulSoup(listing_html, "html.parser")

    tiles = _locate_opportunity_tiles(soup)

    if not tiles:
        logger.info("COTA: no open opportunities found")
        return []

    out: List[RawOpportunity] = []
    timeout = ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for i, tile in enumerate(tiles, 1):
            logger.debug(f"Processing opportunity {i}/{len(tiles)}: {tile['record_id']}")

            await asyncio.sleep(0.1)

            record_id = tile["record_id"]
            original_title = tile["title"]
            due_text_raw = tile["due_text"]
            question_deadline_raw = tile["question_deadline_text"]

            # Parse external ID from title: "25-049 - Project Name"
            match = re.match(
                r"^\s*(?P<sol>[0-9A-Za-z]+[-/][0-9A-Za-z]+)\s*[-:]\s*(?P<title>.+)$",
                original_title.strip()
            )

            if match:
                external_id = match.group("sol").strip()
                clean_title = match.group("title").strip()
            else:
                external_id = record_id or ""
                clean_title = original_title.strip()

            # Parse dates from listing page
            cleaned_due = _clean_date_string(due_text_raw)
            due_dt = _parse_datetime(cleaned_due)

            # NEW: Parse question deadline
            cleaned_question = _clean_date_string(question_deadline_raw)
            question_deadline_dt = _parse_datetime(cleaned_question)

            # Build detail URL with correct parameters
            detail_url = DETAIL_URL_TEMPLATE.format(PID=record_id) if record_id else LIST_URL

            # Fetch detail page
            description_text = ""
            posted_dt = None
            detail_due_dt = None
            attachment_urls: List[str] = []

            if record_id:
                (
                    description_text,
                    posted_dt,
                    detail_due_dt,
                    attachment_urls,
                ) = await _fetch_detail_opportunity(session, detail_url)

            # Use detail due date if available, otherwise listing due date
            final_due = detail_due_dt or due_dt

            # Ensure timezone-aware
            if final_due and final_due.tzinfo is None:
                final_due = final_due.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)

            # Build summary with question deadline
            summary_text = description_text or f"Status: {tile['status']}. Due: {cleaned_due}."
            if question_deadline_dt:
                question_local = question_deadline_dt.astimezone(ZoneInfo("America/New_York")).strftime("%m/%d/%Y %I:%M %p")
                summary_text = f"{summary_text} Question deadline: {question_local}."

            # Classify
            keyword_tag = _classify_keyword_tag(
                clean_title,
                AGENCY_NAME,
                "Transit / Transportation"
            )

            # Generate hash
            hash_body_val = hashlib.sha256(
                f"{external_id}||{clean_title}||{cleaned_due}".encode("utf-8", errors="ignore")
            ).hexdigest()

            # Create opportunity
            out.append(
                RawOpportunity(
                    agency_name=AGENCY_NAME,
                    title=clean_title,
                    summary=summary_text,
                    description=description_text,
                    due_date=final_due,
                    posted_date=posted_dt.astimezone(timezone.utc) if posted_dt and posted_dt.tzinfo else posted_dt,
                    prebid_date=question_deadline_dt,  # Store question deadline as prebid_date
                    source="cota",
                    source_url=safe_source_url(AGENCY_NAME, detail_url, LIST_URL),
                    category="Transit / Transportation",
                    location_geo="Franklin County, OH",
                    attachments=attachment_urls,
                    status="open",
                    hash_body=hash_body_val,
                    external_id=external_id,
                    keyword_tag=keyword_tag,
                    date_added=datetime.now(timezone.utc),
                )
            )

    logger.info(f"COTA: successfully scraped {len(out)} open bid(s)")
    return out


# =============================================================================
# Public API
# =============================================================================

async def get_opportunities() -> List[RawOpportunity]:
    """Get opportunities from COTA."""
    return await _scrape_listing_page()


async def fetch() -> List[RawOpportunity]:
    """Main entry point with optional monitoring."""
    if HAS_MONITORING:
        with ScraperMonitor(source="cota", scraper_version=SCRAPER_VERSION) as monitor:
            opps = await _scrape_listing_page()
            monitor.set_items_scraped(len(opps))
            return opps
    else:
        return await _scrape_listing_page()


# =============================================================================
# Test Runner
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    async def _test():
        print("\n" + "="*80)
        print(f"Testing COTA Scraper v{SCRAPER_VERSION} (FIXED)")
        print("="*80 + "\n")

        opps = await get_opportunities()

        print(f"\n✅ Found {len(opps)} opportunities\n")

        for i, opp in enumerate(opps, 1):
            print(f"{'─'*80}")
            print(f"Opportunity #{i}")
            print(f"{'─'*80}")
            print(f"Solicitation #: {opp.external_id}")
            print(f"Title: {opp.title}")
            print(f"Due: {opp.due_date}")
            print(f"Posted: {opp.posted_date}")
            print(f"Question Deadline: {opp.prebid_date}")  # NEW
            print(f"URL: {opp.source_url}")
            print(f"Attachments: {len(opp.attachments)} file(s)")
            if opp.attachments:
                for att in opp.attachments[:3]:
                    print(f"  - {att}")
            print(f"Summary: {(opp.summary or '')[:200]}...")
            print()

    asyncio.run(_test())
