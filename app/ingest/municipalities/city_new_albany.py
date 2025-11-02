# app/ingest/municipalities/city_new_albany.py
import asyncio
import logging
from datetime import datetime
from typing import List, Optional
import aiohttp
from bs4 import BeautifulSoup
from app.ingest.base import RawOpportunity

logger = logging.getLogger(__name__)

AGENCY_NAME = "City of New Albany"
LIST_URL = "https://www.bidexpress.com/businesses/65374/home"
BASE_URL = "https://www.bidexpress.com"


# --------------------------
# Helpers
# --------------------------

def _parse_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip().replace("UTC", "").strip()
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%m/%d/%y %I:%M %p"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _abs_url(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


# --------------------------
# Scrape main listing
# --------------------------

async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.text()


async def _scrape_listing(session: aiohttp.ClientSession) -> List[RawOpportunity]:
    html = await _fetch_html(session, LIST_URL)
    soup = BeautifulSoup(html, "html.parser")

    # Upcoming solicitations table (open bids)
    table = soup.find("table", id="solicitations")
    if not table:
        logger.warning("New Albany: no solicitation table found.")
        return []

    opps: List[RawOpportunity] = []

    for tr in table.find_all("tr"):
        a_tag = tr.find("a", href=True)
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        href = a_tag["href"]
        url = _abs_url(href)

        desc_tag = a_tag.find_next("div", class_="desc-dialog")
        description = desc_tag.get("data-popup-content", "").strip() if desc_tag else ""

        tds = tr.find_all("td")
        due_str = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        due_dt = _parse_date(due_str)

        opps.append(
            RawOpportunity(
                agency_name=AGENCY_NAME,
                title=title,
                summary=description[:400],
                description=description,
                due_date=due_dt,
                posted_date=None,
                prebid_date=None,
                source=_abs_url(href),
                source_url=_abs_url(href),
                category=AGENCY_NAME,
                location_geo=None,
                attachments=[],
                status="open",
            )
        )

    logger.info(f"New Albany: scraped {len(opps)} active bid(s).")
    return opps


# --------------------------
# Public API
# --------------------------

async def get_opportunities() -> List[RawOpportunity]:
    async with aiohttp.ClientSession() as session:
        return await _scrape_listing(session)


async def fetch() -> List[RawOpportunity]:
    return await get_opportunities()


# --------------------------
# Manual Test
# --------------------------

if __name__ == "__main__":
    async def _test():
        opps = await get_opportunities()
        for o in opps:
            print("----")
            print("Title:", o.title)
            print("Due:", o.due_date)
            print("URL:", o.source_url)
            print("Description:", (o.description or "")[:200])

    asyncio.run(_test())
