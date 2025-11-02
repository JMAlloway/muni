import re
import time
from datetime import datetime, timezone
from typing import List, Optional

from bs4 import BeautifulSoup

# Selenium 4 imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Auto-install the correct ChromeDriver for the actual Chrome version on this box
from webdriver_manager.chrome import ChromeDriverManager

# Use undetected_chromedriver's stealth hardening
import undetected_chromedriver as uc

from app.ingest.base import RawOpportunity

AGENCY_NAME = "Village of Minerva Park"
BASE_URL = "https://www.minervapark.gov"
RFP_URL = f"{BASE_URL}/rfps"


def _build_driver() -> webdriver.Chrome:
    """
    Build a headless Chrome driver matched to the local Chrome version
    (via webdriver_manager) and apply stealth tweaks to reduce bot detection.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    # Pretend to be a normal desktop Chrome 141 on Windows
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    )

    # >>> THIS is the key new part: use a Service with the right driver binary
    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Try to cloak automation fingerprints using uc.Stealth
    try:
        uc.Stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
    except Exception:
        # It's fine if this fails - scraping will still work.
        pass

    return driver


def _parse_posted_date(time_tag) -> datetime:
    """
    <time datetime="2025-10-07T09:19:00-04:00">Tue 10/07/2025</time>
    Priority:
    1. machine 'datetime' attribute
    2. visible MM/DD/YYYY
    3. now()
    """
    if time_tag is None:
        return datetime.utcnow()

    iso_val = time_tag.get("datetime")
    if iso_val:
        try:
            return datetime.fromisoformat(iso_val)
        except Exception:
            pass

    txt = time_tag.get_text(" ", strip=True)
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if m:
        mm, dd, yyyy = m.groups()
        try:
            return datetime(
                year=int(yyyy),
                month=int(mm),
                day=int(dd),
                hour=0,
                minute=0,
                second=0,
            )
        except Exception:
            pass

    return datetime.utcnow()


def _parse_closing_date(txt: str) -> Optional[datetime]:
    """
    e.g. 'Fri 10/31/2025'
    We'll grab MM/DD/YYYY and assume 23:59 so sorting works.
    If we can't parse, return None (UI will show TBD).
    """
    if not txt:
        return None

    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if not m:
        return None

    mm, dd, yyyy = m.groups()
    try:
        return datetime(
            year=int(yyyy),
            month=int(mm),
            day=int(dd),
            hour=23,
            minute=59,
            second=0,
        )
    except Exception:
        return None


def _get_page_html_via_browser(url: str) -> str:
    """
    Launch stealth Chrome that matches local Chrome version,
    visit page, wait ~3 seconds for bot check and table render,
    grab DOM, shut down.
    """
    driver = _build_driver()
    try:
        driver.get(url)
        time.sleep(3)
        return driver.page_source
    finally:
        driver.quit()


def fetch() -> List[RawOpportunity]:
    """
    Browser scrape https://www.minervapark.gov/rfps
    and build RawOpportunity rows for insertion.
    """
    html = _get_page_html_via_browser(RFP_URL)
    soup = BeautifulSoup(html, "html.parser")

    # The RFPs are in a table like:
    # <table class="views-table views-view-table ...">
    #   <thead>
    #     <th>Title</th>
    #     <th>Posted Date</th>
    #     <th>Closing Date</th>
    #   </thead>
    #   <tbody>
    #     <tr> ... </tr>
    #   </tbody>
    # </table>
    table = soup.select_one("table.views-table.views-view-table")
    if not table:
        return []

    rows = table.select("tbody > tr")
    if not rows:
        return []

    out: List[RawOpportunity] = []

    for tr in rows:
        # TITLE / HREF
        title_cell = tr.select_one("td.views-field-title")
        if not title_cell:
            continue

        link_tag = title_cell.select_one("a[href]")
        if link_tag:
            title_text = link_tag.get_text(" ", strip=True)
            href = link_tag.get("href", "")
        else:
            title_text = title_cell.get_text(" ", strip=True)
            href = ""

        if href and not href.lower().startswith("http"):
            detail_url = f"{BASE_URL}{href}"
        else:
            detail_url = href or RFP_URL

        # POSTED DATE
        posted_cell = tr.select_one("td.views-field-created")
        posted_time_tag = posted_cell.select_one("time") if posted_cell else None
        posted_dt = _parse_posted_date(posted_time_tag)

        # DUE / CLOSING DATE
        closing_cell = tr.select_one("td.views-field-field-date")
        closing_txt = closing_cell.get_text(" ", strip=True) if closing_cell else ""
        due_dt = _parse_closing_date(closing_txt)

        # Build RawOpportunity
        opp = RawOpportunity(
            source="minerva_park",
            source_url=detail_url,
            title=title_text,
            summary="",
            description="",
            category="RFP/RFQ",
            agency_name=AGENCY_NAME,
            location_geo="Minerva Park, OH",
            posted_date=posted_dt,
            due_date=due_dt,
            prebid_date=None,
            attachments=[],
            status="open",           # everything on this page is "Open"
            hash_body=None,
            external_id="",          # no solicitation # exposed in listing
            keyword_tag="",
            date_added=datetime.now(timezone.utc),  # 👈 NEW LINE
        )

        out.append(opp)

    return out
