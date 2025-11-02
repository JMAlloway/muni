import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import aiohttp
from bs4 import BeautifulSoup

from app.ingest.base import RawOpportunity

logger = logging.getLogger(__name__)

AGENCY_NAME = "City of Worthington"
LIST_URL = "https://www.worthington.org/Bids.aspx"
BASE_URL = "https://www.worthington.org"


async def _fetch_html(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        return await _fetch(session, url)


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


async def _fetch_detail_description_and_dates_and_attachments(
    session: aiohttp.ClientSession,
    url: str
) -> Tuple[str, Optional[datetime], Optional[datetime], Optional[datetime], List[str]]:

    try:
        html = await _fetch(session, url)
    except Exception as e:
        logger.warning(f"Worthington detail fetch failed {url}: {e}")
        return ("", None, None, None, [])

    soup = BeautifulSoup(html, "html.parser")
    text_all = soup.get_text(" ", strip=True)

    posted_dt = None
    due_dt = None
    prebid_dt = None

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
    if desc_block:
        description_text = desc_block.get_text(" ", strip=True)
    else:
        description_text = text_all

    attachment_urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lower_href = href.lower()
        if any(
            lower_href.endswith(ext)
            for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"]
        ):
            if href.startswith("http://") or href.startswith("https://"):
                attachment_urls.append(href)
            elif href.startswith("/"):
                attachment_urls.append(BASE_URL + href)
            else:
                attachment_urls.append(BASE_URL + "/" + href.lstrip("/"))

    return (description_text, posted_dt, due_dt, prebid_dt, attachment_urls)


def _normalize_detail_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
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

    card_divs = soup.find_all("div", class_="listItemsRow")
    for card in card_divs:
        classes = card.get("class", [])
        if "bid" not in classes:
            continue

        bid_links = [
            a for a in card.find_all("a", href=True)
            if "bidid=" in a["href"].lower()
        ]
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


async def _scrape_listing_page() -> List[RawOpportunity]:
    html = await _fetch_html(LIST_URL)
    soup = BeautifulSoup(html, "html.parser")

    page_text = soup.get_text(" ", strip=True).lower()

    rows = _extract_rows_from_table(soup)
    if not rows:
        rows = _extract_rows_from_cards(soup)

    if not rows:
        if "no open bid postings" in page_text or "no open bids" in page_text:
            logger.info("Worthington: no open bids at this time.")
            return []
        else:
            logger.warning("Worthington: page parsed but no recognizable bid rows found.")
            return []

    seen = set()
    unique_rows: List[tuple] = []
    for (title, detail_url, row_text) in rows:
        if detail_url in seen:
            continue
        seen.add(detail_url)
        unique_rows.append((title, detail_url, row_text))
    rows = unique_rows

    out: List[RawOpportunity] = []

    async with aiohttp.ClientSession() as session:
        for (title, detail_url, row_text) in rows:
            due_dt_row = _parse_date_mmddyyyy(row_text)

            (
                desc,
                posted_dt,
                due_dt_detail,
                prebid_dt,
                attachment_urls,
            ) = await _fetch_detail_description_and_dates_and_attachments(session, detail_url)

            best_summary = desc or row_text
            best_due = due_dt_detail or due_dt_row

            out.append(
                RawOpportunity(
                    agency_name=AGENCY_NAME,
                    title=title,
                    summary=best_summary,
                    description=desc,
                    due_date=best_due,
                    posted_date=posted_dt,
                    prebid_date=prebid_dt,
                    source=detail_url,
                    source_url=detail_url,
                    category=AGENCY_NAME,
                    location_geo=None,
                    attachments=attachment_urls,
                    status="open",
                    date_added=datetime.now(timezone.utc),  # 👈 NEW LINE
                )
            )

    logger.info(f"Worthington: scraped {len(out)} bid(s).")
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
            print("title:", o.title)
            print("due:", o.due_date)
            print("url:", o.source_url)
            print("posted:", o.posted_date)
            print("prebid:", o.prebid_date)
            print("attachments:", o.attachments)
            print("summary:", (o.summary or "")[:200], "...")
            print()

    asyncio.run(_test())
