import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup
from app.ingest.base import RawOpportunity

logger = logging.getLogger(__name__)

AGENCY_NAME = "City of Gahanna"
BASE_URL = "https://www.gahanna.gov"
LIST_URL = f"{BASE_URL}/Bids.aspx"

# --------------------------
# helpers
# --------------------------

async def _fetch(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.text()

def _parse_date_mmddyyyy(text_in: str) -> Optional[datetime]:
    if not text_in:
        return None
    lower = text_in.lower()
    if "open until contracted" in lower or "upon contract" in lower:
        return None

    parts = text_in.replace("\xa0", " ").split()
    for i, token in enumerate(parts):
        if token.count("/") == 2:
            mm, dd, yyyy = token.split("/")
            if len(yyyy) == 4 and yyyy.isdigit():
                # try "MM/DD/YYYY HH:MM AM/PM"
                if i + 2 < len(parts):
                    maybe_combo = f"{token} {parts[i+1]} {parts[i+2]}"
                    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M %p"):
                        try:
                            return datetime.strptime(maybe_combo, fmt)
                        except ValueError:
                            pass
                # try just "MM/DD/YYYY"
                try:
                    return datetime.strptime(token, "%m/%d/%Y")
                except ValueError:
                    pass
    return None

def _normalize_detail_url(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    return f"{BASE_URL}/{href.lstrip('/')}"

def _classify_keyword_tag(title: str, agency: str, default_val: str = "General / City Bid") -> str:
    t = f"{title} {agency}".lower()
    if "paving" in t or "asphalt" in t or "road" in t:
        return "Paving / Streets"
    if "vehicle" in t or "truck" in t:
        return "Fleet / Vehicles"
    if "police" in t or "fire" in t:
        return "Public Safety"
    if "network" in t or "software" in t or "technology" in t:
        return "IT / Technology"
    return default_val

# --------------------------
# detail page scrape
# --------------------------

async def _fetch_detail(
    session: aiohttp.ClientSession,
    url: str
) -> Tuple[str, Optional[datetime], Optional[datetime], Optional[datetime], List[str], str]:
    """
    Return:
        description_text (long narrative under Description:)
        posted_dt        (Publication Date/Time)
        due_dt           (Closing Date/Time)
        prebid_dt        (if present)
        attachment_urls  (list[str])
        external_id      (Bid Number like "825-5", or "" if missing)
    """
    try:
        html = await _fetch(session, url)
    except Exception as e:
        logger.warning(f"Gahanna detail fetch failed {url}: {e}")
        return ("", None, None, None, [], "")

    soup = BeautifulSoup(html, "html.parser")

    # Bid Number lives in <span class="BidDetailSpec">825-5<br></span>
    external_id = ""
    spec_span = soup.find("span", class_="BidDetailSpec")
    if spec_span:
        external_id = spec_span.get_text(" ", strip=True)
        external_id = external_id.replace("\n", " ").replace("\r", " ").strip()

    # Find the "Bid Details" table with Description:, Publication Date/Time:, etc.
    bid_details_table = None
    for tbl in soup.find_all("table"):
        summary_val = (tbl.get("summary") or "").strip().lower()
        if "bid details" in summary_val:
            bid_details_table = tbl
            break

    description_text = ""
    posted_dt = None
    due_dt = None
    prebid_dt = None
    attachment_urls: List[str] = []

    if bid_details_table:
        rows = bid_details_table.find_all("tr")
        pending_label = None

        for tr in rows:
            tds = tr.find_all("td")
            if not tds:
                continue

            # label row?
            label_span = tds[0].find("span", class_="BidListHeader")
            if label_span:
                label_text = label_span.get_text(" ", strip=True)
                label_text = label_text.rstrip(":").strip().lower()
                pending_label = label_text
                continue

            # value row (for the last label we saw)
            value_cell = tds[0]

            if pending_label == "description":
                desc_span = value_cell.find("span", class_="BidDetail")
                if desc_span:
                    description_text = desc_span.get_text(" ", strip=True)

            elif pending_label and pending_label.startswith("publication"):
                pub_text = value_cell.get_text(" ", strip=True)
                posted_dt = _parse_date_mmddyyyy(pub_text)

            elif pending_label and pending_label.startswith("closing"):
                close_text = value_cell.get_text(" ", strip=True)
                due_dt = _parse_date_mmddyyyy(close_text)

            elif pending_label and ("pre-bid" in pending_label or "pre bid" in pending_label):
                prebid_text = value_cell.get_text(" ", strip=True)
                prebid_dt = _parse_date_mmddyyyy(prebid_text)

            elif pending_label and pending_label.startswith("related document"):
                related_div = value_cell.find("div", class_="relatedDocuments")
                if related_div:
                    for a in related_div.find_all("a"):
                        href = a.get("href")
                        if not href:
                            continue
                        href = href.strip()
                        lower_href = href.lower()
                        if lower_href.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
                            abs_url = _normalize_detail_url(href)
                            if abs_url:
                                attachment_urls.append(abs_url)

            pending_label = None

    # fallback description if we didn't get it from Description:
    if not description_text:
        generic_desc = soup.find("span", class_="BidDetail")
        if generic_desc:
            description_text = generic_desc.get_text(" ", strip=True)
        else:
            description_text = soup.get_text(" ", strip=True)

    # dedupe attachments
    attachment_urls = list(dict.fromkeys(attachment_urls))

    return (description_text, posted_dt, due_dt, prebid_dt, attachment_urls, external_id)

# --------------------------
# listing scrape
# --------------------------

async def _scrape_listing_page() -> List[RawOpportunity]:
    async with aiohttp.ClientSession() as session:
        html = await _fetch(session, LIST_URL)
        soup = BeautifulSoup(html, "html.parser")

        rows: List[tuple] = []

        # Look for rows in tables
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                link = tr.find("a", href=True)
                if not link:
                    continue
                href = link.get("href")
                if not href or "bidid=" not in href.lower():
                    continue

                detail_url = _normalize_detail_url(href)
                if not detail_url:
                    continue

                title = link.get_text(strip=True)
                row_text = " ".join(td.get_text(" ", strip=True) for td in tds)
                rows.append((title, detail_url, row_text))

        # Fallback: div cards
        if not rows:
            for card in soup.find_all("div", class_="listItemsRow"):
                link = card.find("a", href=True)
                if not link:
                    continue
                href = link.get("href")
                if not href or "bidid=" not in href.lower():
                    continue

                detail_url = _normalize_detail_url(href)
                if not detail_url:
                    continue

                title = link.get_text(strip=True)
                row_text = card.get_text(" ", strip=True)
                rows.append((title, detail_url, row_text))

        if not rows:
            page_text_lower = soup.get_text(" ", strip=True).lower()
            if "no open bid postings" in page_text_lower or "no open bids" in page_text_lower:
                logger.info("Gahanna: no open bids at this time.")
                return []
            logger.warning("Gahanna: page parsed but no recognizable bid rows found.")
            return []

        # dedupe by detail_url
        seen = set()
        unique_rows = []
        for (title, detail_url, row_text) in rows:
            if detail_url in seen:
                continue
            seen.add(detail_url)
            unique_rows.append((title, detail_url, row_text))

        out: List[RawOpportunity] = []

        for (title, detail_url, row_text) in unique_rows:
            due_dt_row = _parse_date_mmddyyyy(row_text)

            (
                long_desc,
                posted_dt,
                due_dt_detail,
                prebid_dt,
                attachment_urls,
                external_id,
            ) = await _fetch_detail(session, detail_url)

            final_due = due_dt_detail or due_dt_row

            # If there's still no Bid Number, we want to store "Unknown"
            if not external_id or not external_id.strip():
                external_id = "Unknown"

            keyword_tag = _classify_keyword_tag(title, AGENCY_NAME)
            hash_body = hashlib.sha256(
                f"{external_id}|{title}|{final_due}|{long_desc}".encode("utf-8", errors="ignore")
            ).hexdigest()

            out.append(
                RawOpportunity(
                    source="city_gahanna",
                    source_url=detail_url,
                    agency_name=AGENCY_NAME,
                    location_geo="Franklin County, OH",
                    title=title,
                    summary=long_desc[:250] if long_desc else title,
                    description=long_desc,
                    category="General / City Bid",
                    posted_date=posted_dt,
                    due_date=final_due,
                    prebid_date=prebid_dt,
                    attachments=attachment_urls,
                    status="open",
                    hash_body=hash_body,
                    external_id=external_id,
                    keyword_tag=keyword_tag,
                    date_added=datetime.now(timezone.utc),  # 👈 NEW LINE
                )
            )

        logger.info(f"Gahanna: scraped {len(out)} bid(s).")
        return out

# THIS IS CRITICAL FOR runner.py
async def fetch() -> List[RawOpportunity]:
    return await _scrape_listing_page()

if __name__ == "__main__":
    asyncio.run(_scrape_listing_page())
