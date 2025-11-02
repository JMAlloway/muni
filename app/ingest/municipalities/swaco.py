import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup

from app.ingest.base import RawOpportunity

logger = logging.getLogger(__name__)

AGENCY_NAME = "Solid Waste Authority of Central Ohio (SWACO)"
LIST_URL = "https://www.swaco.org/Bids.aspx"
BASE_URL = "https://www.swaco.org"


# --------------------------
# HTTP fetch
# --------------------------

async def _fetch_html(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        return await _fetch(session, url)


async def _fetch(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.text()


# --------------------------
# Date parsing
# --------------------------

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
            if len(mm) in (1, 2) and len(dd) in (1, 2) and len(yyyy) == 4 and yyyy.isdigit():
                if i + 2 < len(parts):
                    t_part = parts[i + 1]
                    ampm = parts[i + 2]
                    comb = f"{token} {t_part} {ampm}"
                    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M %p"):
                        try:
                            return datetime.strptime(comb, fmt)
                        except ValueError:
                            pass
                try:
                    return datetime.strptime(token, "%m/%d/%Y")
                except ValueError:
                    pass
    return None


def _parse_posted_date(text_in: str) -> Optional[datetime]:
    return _parse_date_mmddyyyy(text_in)


def _parse_prebid_date(text_in: str) -> Optional[datetime]:
    return _parse_date_mmddyyyy(text_in)


# --------------------------
# Bid number extraction
# --------------------------

_BID_NO_REGEXES = [
    # Bid No. 8045
    re.compile(r"bid\s*no\.?\s*[:#]?\s*([A-Za-z0-9\-/\.]+)", re.IGNORECASE),
    # Bid Number: 8045
    re.compile(r"bid\s*number\.?\s*[:#]?\s*([A-Za-z0-9\-/\.]+)", re.IGNORECASE),
    # Sometimes they smash it: "Bid No.8045"
    re.compile(r"bid\s*no\.?([0-9]{3,})", re.IGNORECASE),
]


def _run_bid_regex(text: str) -> Optional[str]:
    for rx in _BID_NO_REGEXES:
        m = rx.search(text)
        if m:
            return m.group(1).strip()
    return None


def _extract_bid_number(soup: BeautifulSoup, url: str = "") -> Optional[str]:
    """
    Make this as robust as we can:
    - look for any element that has "Bid No" or "Bid Number"
    - then run regex on that element's text
    - if no luck, run regex on the whole page text
    """
    # 1) any obvious tags that might carry "Bid No."
    candidates = []

    # spans/divs/p
    for tag in soup.find_all(["span", "div", "p", "li", "h1", "h2", "h3"]):
        txt = tag.get_text(" ", strip=True)
        if "bid no" in txt.lower() or "bid number" in txt.lower():
            candidates.append(txt)

    for txt in candidates:
        num = _run_bid_regex(txt)
        if num:
            return num

    # 2) try the whole page text
    full_text = soup.get_text(" ", strip=True)
    num = _run_bid_regex(full_text)
    if num:
        return num

    # 3) last resort: sometimes CivicPlus puts it in the page title
    title_tag = soup.find("title")
    if title_tag:
        num = _run_bid_regex(title_tag.get_text(" ", strip=True))
        if num:
            return num

    # 4) log miss so we can see it in your console
    logger.debug(f"SWACO: could not find Bid No. on page {url}")
    return None


# --------------------------
# Detail page
# --------------------------

async def _fetch_detail_description_and_dates_and_attachments(
    session: aiohttp.ClientSession,
    url: str
) -> Tuple[str, Optional[datetime], Optional[datetime], Optional[datetime], List[str], Optional[str]]:
    try:
        html = await _fetch(session, url)
    except Exception as e:
        logger.warning(f"SWACO detail fetch failed {url}: {e}")
        return ("", None, None, None, [], None)

    soup = BeautifulSoup(html, "html.parser")
    text_all = soup.get_text(" ", strip=True)

    posted_dt, due_dt, prebid_dt = None, None, None

    def grab_after(label: str, blob: str, window: int = 8) -> str:
        lower_blob = blob.lower()
        label_lower = label.lower()
        if label_lower not in lower_blob:
            return ""
        tokens = blob.split()
        for idx, tok in enumerate(tokens):
            if tok.lower().startswith(label_lower.replace(":", "")):
                return " ".join(tokens[idx + 1: idx + 1 + window])
        return ""

    posted_hint = grab_after("Publication", text_all)
    posted_dt = _parse_posted_date(posted_hint)

    due_hint = grab_after("Closing", text_all)
    if not due_hint:
        due_hint = grab_after("Closing Date", text_all)
    due_dt = _parse_date_mmddyyyy(due_hint)

    prebid_hint = grab_after("Pre-Bid", text_all)
    prebid_dt = _parse_prebid_date(prebid_hint)

    desc_block = soup.find(class_="bidDetail")
    if not desc_block:
        desc_block = soup.find("div", {"id": "content"}) or soup.find("div", {"role": "main"})
    description_text = desc_block.get_text(" ", strip=True) if desc_block else text_all

    # attachments
    attachment_urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lower_href = href.lower()
        if any(lower_href.endswith(ext) for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"]):
            if href.startswith("http"):
                attachment_urls.append(href)
            elif href.startswith("/"):
                attachment_urls.append(BASE_URL + href)
            else:
                attachment_urls.append(BASE_URL + "/" + href.lstrip("/"))

    # NOW: extract bid number with the robust routine
    bid_no = _extract_bid_number(soup, url=url)

    return (description_text, posted_dt, due_dt, prebid_dt, attachment_urls, bid_no)


# --------------------------
# Listing page helpers
# --------------------------

def _normalize_detail_url(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href.lstrip("/")


def _extract_rows_from_table(soup: BeautifulSoup) -> List[tuple]:
    rows: List[tuple] = []
    for table in soup.find_all("table"):
        header_text = table.get_text(" ", strip=True).lower()
        if "closing date" not in header_text and "bid title" not in header_text:
            continue
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            link_tag = tr.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if "bidid=" not in href.lower():
                continue
            title = link_tag.get_text(strip=True)
            detail_url = _normalize_detail_url(href)
            row_text = " ".join(td.get_text(" ", strip=True) for td in tds)
            rows.append((title, detail_url, row_text))
    return rows


def _extract_rows_from_cards(soup: BeautifulSoup) -> List[tuple]:
    rows: List[tuple] = []
    for card in soup.find_all("div", class_="listItemsRow"):
        classes = card.get("class", [])
        if "bid" not in classes:
            continue
        bid_links = [a for a in card.find_all("a", href=True) if "bidid=" in a["href"].lower()]
        if not bid_links:
            continue
        main_link = bid_links[0]
        href = main_link["href"]
        title = main_link.get_text(strip=True)
        if not title:
            continue
        detail_url = _normalize_detail_url(href)
        row_text = card.get_text(" ", strip=True)
        rows.append((title, detail_url, row_text))
    return rows


# --------------------------
# Main scrape
# --------------------------

async def _scrape_listing_page() -> List[RawOpportunity]:
    html = await _fetch_html(LIST_URL)
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True).lower()

    rows = _extract_rows_from_table(soup)
    if not rows:
        rows = _extract_rows_from_cards(soup)

    if not rows:
        if "no open bid postings" in page_text or "no open bids" in page_text:
            logger.info("SWACO: no open bids at this time.")
            return []
        logger.warning("SWACO: page parsed but no recognizable bid rows found.")
        return []

    seen, out = set(), []
    unique_rows = [(t, u, r) for (t, u, r) in rows if not (u in seen or seen.add(u))]

    async with aiohttp.ClientSession() as session:
        for (title, detail_url, row_text) in unique_rows:
            due_dt_row = _parse_date_mmddyyyy(row_text)

            (
                desc,
                posted_dt,
                due_dt_detail,
                prebid_dt,
                attachment_urls,
                bid_no,
            ) = await _fetch_detail_description_and_dates_and_attachments(session, detail_url)

            best_summary = desc or row_text
            best_due = due_dt_detail or due_dt_row

            display_title = f"{bid_no} {title}".strip() if bid_no else title

            out.append(
                RawOpportunity(
                    agency_name=AGENCY_NAME,
                    title=display_title,
                    summary=best_summary,
                    description=desc,
                    due_date=best_due,
                    posted_date=posted_dt,
                    prebid_date=prebid_dt,
                    source=detail_url,
                    source_url=detail_url,
                    # you can swap this to your new taxonomy
                    category="Solid Waste / Recycling / Environmental",
                    location_geo=None,
                    attachments=attachment_urls,
                    status="open",
                    date_added=datetime.now(timezone.utc),
                    external_id=bid_no if bid_no else None,
                )
            )

    logger.info(f"SWACO: scraped {len(out)} bid(s).")
    return out


# --------------------------
# Public entrypoints
# --------------------------

async def get_opportunities() -> List[RawOpportunity]:
    return await _scrape_listing_page()


async def fetch() -> List[RawOpportunity]:
    return await get_opportunities()


# --------------------------
# Local test
# --------------------------

if __name__ == "__main__":
    async def _test():
        opps = await get_opportunities()
        for o in opps:
            print("-----")
            print("title:", o.title)
            print("external_id:", getattr(o, "external_id", None))
            print("due:", o.due_date)
            print("url:", o.source_url)
            print("posted:", o.posted_date)
            print("prebid:", o.prebid_date)
            print("attachments:", o.attachments)
            print("summary:", (o.summary or "")[:200], "...")
            print()

    asyncio.run(_test())
