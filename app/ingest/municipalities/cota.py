import asyncio
import logging
import re
import hashlib
from datetime import datetime
from typing import List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup

from app.ingest.base import RawOpportunity
from app.ingest.municipalities.city_columbus import _classify_keyword_tag
from app.ingest.utils import safe_source_url

logger = logging.getLogger(__name__)

AGENCY_NAME = "Central Ohio Transit Authority (COTA)"
BASE_URL = "https://cota.dbesystem.com"
LIST_URL = BASE_URL + "/FrontEnd/proposalsearchpublic.asp"

# We'll fill in the {RID} token with the record id pulled from ViewDetail('RID')
DETAIL_URL_TEMPLATE = BASE_URL + "/FrontEnd/ProposalSearchPublicDetail.asp?TN=cota&RID={RID}"


# ---------------------------------
# HTTP helpers with encoding fix
# ---------------------------------

async def _read_text_with_fallback(resp: aiohttp.ClientResponse) -> str:
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
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href.lstrip("/")


# ---------------------------------
# Date parsing utilities
# ---------------------------------

def _clean_due_string(raw_text: str) -> str:
    text = raw_text
    text = re.sub(r"\bUS/Eastern\b", "", text, flags=re.IGNORECASE)
    text = text.strip()

    if text.lower().startswith("due "):
        text = text[4:].strip()

    return text


def _parse_due_datetime(raw_text: str) -> Optional[datetime]:
    cleaned = " ".join(raw_text.split())
    if not cleaned:
        return None

    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M %p"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass

    try:
        return datetime.strptime(cleaned, "%m/%d/%Y")
    except ValueError:
        return None


# ---------------------------------
# Detail page parsing
# ---------------------------------

def _extract_detail_description_dates_attachments(
    soup: BeautifulSoup,
) -> Tuple[str, Optional[datetime], Optional[datetime], List[str]]:
    page_text = soup.get_text(" ", strip=True)
    description_text = " ".join(page_text.split())

    posted_date = None
    due_date = None

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        label = cells[0].get_text(" ", strip=True).lower()
        value_text = cells[1].get_text(" ", strip=True)

        if any(key in label for key in ["closing", "due", "proposal due", "closing date"]):
            due_candidate = _parse_due_datetime(_clean_due_string(value_text))
            if due_candidate:
                due_date = due_candidate

        if any(key in label for key in ["post", "publish", "issued", "release"]):
            posted_candidate = _parse_due_datetime(value_text)
            if posted_candidate:
                posted_date = posted_candidate

    attachment_urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lower = href.lower()
        if any(
            lower.endswith(ext)
            for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"]
        ):
            attachment_urls.append(_abs_url(href))

    return (description_text, posted_date, due_date, attachment_urls)


async def _fetch_detail_opportunity(
    session: aiohttp.ClientSession,
    detail_url: str
) -> Tuple[str, Optional[datetime], Optional[datetime], List[str]]:
    try:
        html = await _fetch(session, detail_url)
    except Exception as e:
        logger.warning(f"COTA detail fetch failed {detail_url}: {e}")
        return ("", None, None, [])

    soup = BeautifulSoup(html, "html.parser")
    return _extract_detail_description_dates_attachments(soup)


# ---------------------------------
# Listing page parsing
# ---------------------------------

def _locate_opportunity_tiles(soup: BeautifulSoup) -> List[dict]:
    results: List[dict] = []

    tiles = soup.find_all("a", class_="RecordTile")
    for tile in tiles:
        href_val = tile.get("href", "")
        m = re.search(r"ViewDetail\('([^']+)'\)", href_val)
        record_id = m.group(1).strip() if m else None

        desc_div = tile.find("div", class_="Description")
        if not desc_div:
            continue

        status_div = desc_div.find("div", class_="Status")
        status_text = status_div.get_text(" ", strip=True) if status_div else ""
        status_clean = status_text.strip().lower()

        # accept Open or Due Soon
        if status_clean not in ("open", "due soon"):
            continue

        due_div = desc_div.find("div", class_="DateDue")
        due_div_text = due_div.get_text(" ", strip=True) if due_div else ""

        raw_full_desc_text = desc_div.get_text(" ", strip=True)

        date_box = desc_div.find("div", class_="DateBox")
        date_box_text = date_box.get_text(" ", strip=True) if date_box else ""
        if date_box_text:
            raw_full_desc_text = raw_full_desc_text.replace(date_box_text, "").strip()

        if status_text:
            raw_full_desc_text = raw_full_desc_text.replace(status_text, "").strip()

        title_text = " ".join(raw_full_desc_text.split())

        results.append(
            {
                "record_id": record_id,
                "title": title_text,
                "due_text": due_div_text,
                "status": status_text,
            }
        )

    return results


async def _scrape_listing_page() -> List[RawOpportunity]:
    listing_html = await _fetch_html(LIST_URL)
    soup = BeautifulSoup(listing_html, "html.parser")

    tiles = _locate_opportunity_tiles(soup)

    if not tiles:
        logger.info("COTA: no open opportunities found.")
        return []

    out: List[RawOpportunity] = []

    async with aiohttp.ClientSession() as session:
        for tile in tiles:
            record_id = tile["record_id"]
            original_title = tile["title"]
            due_text_raw = tile["due_text"]

            m = re.match(
                r"^\s*(?P<sol>[0-9A-Za-z]+[-/][0-9A-Za-z]+)\s*[-:]\s*(?P<title>.+)$",
                original_title.strip()
            )

            if m:
                external_id = m.group("sol").strip()
                clean_title = m.group("title").strip()
            else:
                external_id = (record_id or "").strip()
                clean_title = original_title.strip()

            cleaned_due = _clean_due_string(due_text_raw)
            due_dt = _parse_due_datetime(cleaned_due)

            detail_url = DETAIL_URL_TEMPLATE.format(RID=record_id) if record_id else LIST_URL

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

            final_due = detail_due_dt or due_dt

            summary_text = (
                description_text
                or f"Status: {tile['status']}. Due: {cleaned_due}."
            )

            keyword_tag = _classify_keyword_tag(
                clean_title,
                AGENCY_NAME,
                "Transit / Transportation"
            )

            hash_body_val = hashlib.sha256(
                f"{external_id}||{clean_title}||{cleaned_due}".encode("utf-8", errors="ignore")
            ).hexdigest()

            out.append(
                RawOpportunity(
                    agency_name=AGENCY_NAME,
                    title=clean_title,
                    summary=summary_text,
                    description=description_text,
                    due_date=final_due,
                    posted_date=posted_dt,
                    prebid_date=None,

                    source="cota",
                    source_url=safe_source_url(AGENCY_NAME, detail_url, LIST_URL),
                    category="Transit / Transportation",
                    location_geo="Franklin County, OH",
                    attachments=attachment_urls,
                    status="open",

                    hash_body=hash_body_val,
                    external_id=external_id,
                    keyword_tag=keyword_tag,
                )
            )

    logger.info(f"COTA: scraped {len(out)} open bid(s).")
    return out


async def get_opportunities() -> List[RawOpportunity]:
    return await _scrape_listing_page()


async def fetch() -> List[RawOpportunity]:
    return await get_opportunities()


if __name__ == "__main__":
    async def _test():
        opps = await get_opportunities()
        for o in opps:
            print("-----")
            print("Solicitation #:", o.external_id)
            print("title:", o.title)
            print("due:", o.due_date)
            print("posted:", o.posted_date)
            print("url:", o.source_url)
            print("attachments:", o.attachments)
            print("summary:", (o.summary or "")[:240], "...")
            print()

    asyncio.run(_test())
