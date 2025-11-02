# app/ingest/municipalities/city_columbus.py
import os
import time
import asyncio
import logging
import hashlib  # <<< added
from datetime import datetime, timezone
from typing import List, Optional, Iterator

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from app.ingest.utils import safe_source_url


# Optional: undetected_chromedriver; we default to plain Selenium for stability
try:
    import undetected_chromedriver as uc  # type: ignore
    _HAS_UC = True
except Exception:
    _HAS_UC = False
    from selenium import webdriver
    # ChromeService + ChromeDriverManager imported inside fallback branch

from app.ingest.base import RawOpportunity  # NOTE: RawOpportunity now includes external_id

# ------------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------------
LIST_URL       = "https://columbusvendorservices.powerappsportals.com/OpenRFQs/"
AGENCY_NAME    = "City of Columbus"
LOCATION       = "Franklin County, OH"

HEADFUL_DEBUG  = False    # show browser while stabilizing; set False in prod
FORCE_SELENIUM = True     # keep True for reliability on this portal; flip False if you want UC
PAGE_TIMEOUT_S = 60
WAIT_TIMEOUT_S = 15
GLOBAL_HARD_STOP_S = 90

BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HTML_DUMP  = os.path.join(BASE_DIR, "columbus_openrfqs.html")
SHOT_DIR   = os.path.join(BASE_DIR, "debug_shots")
os.makedirs(SHOT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [columbus] %(levelname)s: %(message)s")
log = logging.getLogger("columbus")

# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------

def _classify_keyword_tag(title: str, dept: str, typ: str) -> str:
    """
    Very dumb keyword pass for now. You can expand this list over time.
    We'll look at title + dept + typ all lowercased.
    """
    blob = f"{title} {dept} {typ}".lower()

    KEYWORDS = [
        ("hvac",        "HVAC"),
        ("air handler", "HVAC"),
        ("rooftop unit", "HVAC"),
        ("chiller",     "HVAC"),
        ("boiler",      "HVAC"),

        ("electrical",  "Electrical"),
        ("lighting",    "Electrical"),
        ("led retrofit","Electrical"),
        ("generator",   "Electrical"),

        ("plumbing",    "Plumbing"),
        ("sewer",       "Plumbing"),
        ("storm sewer", "Plumbing"),
        ("sanitary",    "Plumbing"),
        ("water line",  "Plumbing"),
        ("hydrant",     "Plumbing"),

        ("asphalt",     "Paving / Asphalt"),
        ("paving",      "Paving / Asphalt"),
        ("resurface",   "Paving / Asphalt"),
        ("mill & fill", "Paving / Asphalt"),
        ("concrete",    "Paving / Asphalt"),   # you can split concrete later if you want

        ("mowing",      "Landscaping / Grounds"),
        ("landscap",    "Landscaping / Grounds"),
        ("turf",        "Landscaping / Grounds"),
        ("tree removal","Landscaping / Grounds"),
        ("snow removal","Landscaping / Grounds"),
        ("salt",        "Landscaping / Grounds"),

        ("network",     "IT / Networking"),
        ("firewall",    "IT / Networking"),
        ("server",      "IT / Networking"),
        ("switches",    "IT / Networking"),
        ("camera",      "Security / Cameras"),
        ("surveillance","Security / Cameras"),

        ("police vehicle", "Vehicles / Fleet"),
        ("patrol vehicle", "Vehicles / Fleet"),
        ("pickup truck",   "Vehicles / Fleet"),
        ("dump truck",     "Vehicles / Fleet"),

        ("uniform",     "Uniforms / Apparel"),
        ("janitorial",  "Janitorial / Cleaning"),
        ("cleaning",    "Janitorial / Cleaning"),
        ("supplies",    "General Supplies"),
        ("office",      "General Supplies"),
        ("print",       "Printing / Signage"),
        ("signage",     "Printing / Signage"),
        ("banner",      "Printing / Signage"),
        ("foam board",  "Printing / Signage"),
    ]

    for needle, label in KEYWORDS:
        if needle in blob:
            return label

    return ""  # default blank, means "uncategorized"

def _parse_date(text: str) -> Optional[datetime]:
    """Fallback parser for human-readable dates like '10/21/2025, 8:00:00 AM'."""
    if not text:
        return None
    t = (
        text.strip()
        .replace("ET", "")
        .replace("et", "")
        .replace("at", " ")
        .replace("  ", " ")
    )
    fmts = [
        "%m/%d/%Y, %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m/%d/%Y, %I.%M.%S %p",
    ]
    for f in fmts:
        try:
            return datetime.strptime(t, f)
        except Exception:
            continue
    return None


def _parse_epoch_attr(attr: str) -> Optional[datetime]:
    """Prefer the DataTables 'data-order' epoch (seconds since Unix epoch)."""
    try:
        if not attr:
            return None
        return datetime.fromtimestamp(int(attr), tz=timezone.utc)
    except Exception:
        return None


def _shot(driver: WebDriver, name: str) -> None:
    try:
        p = os.path.join(SHOT_DIR, f"{int(time.time())}_{name}.png")
        driver.save_screenshot(p)
        log.info("Saved screenshot: %s", p)
    except Exception:
        pass


def _dump_html(driver: WebDriver) -> None:
    try:
        with open(HTML_DUMP, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        log.info("Dumped HTML: %s", HTML_DUMP)
    except Exception:
        pass


def _new_driver() -> WebDriver:
    """Create a Chrome driver. Defaults to plain Selenium for reliability on Power Pages."""
    use_plain = FORCE_SELENIUM or not _HAS_UC

    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    if not use_plain:
        # UC branch (optional)
        opts = uc.ChromeOptions()
        if not HEADFUL_DEBUG:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--window-size=1500,1000")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--lang=en-US,en")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument(f"--user-agent={ua}")
        # Quiet logs
        opts.add_argument("--log-level=3")
        try:
            opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        except Exception:
            pass
        driver = uc.Chrome(options=opts)
    else:
        # Plain Selenium + webdriver-manager (import inside this branch)
        from selenium import webdriver  # ensure available here even if UC imported above
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager

        opts = webdriver.ChromeOptions()
        if not HEADFUL_DEBUG:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--window-size=1500,1000")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--lang=en-US,en")
        opts.add_argument(f"--user-agent={ua}")
        # Quiet logs
        opts.add_argument("--log-level=3")
        try:
            opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        except Exception:
            pass

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)

    driver.set_page_load_timeout(PAGE_TIMEOUT_S)
    driver.implicitly_wait(0)
    return driver


def _rows(scope: WebDriver):
    return scope.find_elements(By.CSS_SELECTOR, "table tbody tr")


def _row_key(tr) -> str:
    """Stable key for detecting page changes (first cell RFQ ID)."""
    try:
        tds = tr.find_elements(By.TAG_NAME, "td")
        return (tds[0].text or "").strip()
    except Exception:
        return ""


def _find_next(scope: WebDriver):
    # DataTables "Next" variations (including common *_next id)
    candidates = [
        (By.CSS_SELECTOR, "#OpenRFQs_next:not(.disabled) a, #OpenRFQs_next:not(.disabled)"),
        (By.CSS_SELECTOR, ".dataTables_paginate .next:not(.disabled) a"),
        (By.CSS_SELECTOR, "li.next:not(.disabled) a, li.pagination-next:not(.disabled) a"),
        (By.XPATH, "//a[contains(., 'Next') and not(contains(@aria-disabled,'true'))]"),
        (By.XPATH, "//button[contains(., 'Next') and not(@disabled)]"),
    ]
    for by, sel in candidates:
        els = scope.find_elements(by, sel)
        if els:
            return els[0]
    return None


def _switch_contexts(driver: WebDriver) -> Iterator[WebDriver]:
    """
    Yield main document; keep iframe scan for future-proofing (currently none present).
    """
    yield driver
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for fr in frames:
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(fr)
            if _rows(driver):
                yield driver
        except Exception:
            continue
    driver.switch_to.default_content()


def _make_hash(rfq_id: str, dept: str, title: str, typ: str, due_txt: str) -> str:
    """
    Build a content hash for change detection and dedupe in downstream storage.
    """
    raw = f"{rfq_id}||{dept}||{title}||{typ}||{due_txt}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


# ------------------------------------------------------------------------------------
# Main scraper: parse the table rows directly (no modal clicking)
# ------------------------------------------------------------------------------------
def fetch_sync() -> List[RawOpportunity]:
    items: List[RawOpportunity] = []
    driver = _new_driver()
    wait = WebDriverWait(driver, WAIT_TIMEOUT_S)
    t0 = time.time()

    def _hard_guard():
        if time.time() - t0 > GLOBAL_HARD_STOP_S:
            _dump_html(driver)
            _shot(driver, "hard_stop")
            raise TimeoutError("OpenRFQs table did not appear within the hard time limit.")

    try:
        log.info("Navigating to %s", LIST_URL)
        driver.get(LIST_URL)
        time.sleep(1.0)

        # FIRST PAGE: robust polling
        start_poll = time.time()
        rows_seen = 0
        while time.time() - start_poll < 30:  # 30s timeout
            trs = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            rows_seen = len(trs)
            print(f"Row probe: {rows_seen} rows")
            if rows_seen > 0:
                break
            time.sleep(0.5)

        if rows_seen == 0:
            _dump_html(driver)
            _shot(driver, "no_rows_first_page")
            raise TimeoutError(
                "No rows found in 30s on first page — see HTML dump for actual DOM."
            )

        # Iterate through main doc (and any frames if they add them later)
        for ctx in _switch_contexts(driver):
            try:
                wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
                )
            except Exception:
                _hard_guard()
                continue

            page_num = 0
            seen_ids = set()
            max_pages = 200  # safety ceiling

            while True:
                page_num += 1
                rows = _rows(ctx)
                if not rows:
                    print(f"Page {page_num}: no rows; stopping.")
                    break

                # Collect rows on this page
                added = 0
                for r in rows:
                    try:
                        tds = r.find_elements(By.TAG_NAME, "td")
                        if len(tds) < 5:
                            continue

                        # Column map based on what you captured:
                        # [0] = RFQ number / Solicitation #
                        # [1] = Department
                        # [2] = Title
                        # [3] = Type (Construction / Goods / etc.)
                        # [4] = Expiry / Due (cell has data-order = epoch seconds)
                        rfq_id   = (tds[0].text or "").strip()
                        dept     = (tds[1].text or "").strip()
                        title    = (tds[2].text or "").strip()
                        typ      = (tds[3].text or "").strip()

                        due_cell = tds[4]
                        due_txt  = (due_cell.text or "").strip()
                        due_ord  = due_cell.get_attribute("data-order") or ""
                        due_dt   = _parse_epoch_attr(due_ord) or _parse_date(due_txt)
                        keyword_tag = _classify_keyword_tag(title, dept, typ)

                        # skip duplicates across pagination
                        if rfq_id and rfq_id in seen_ids:
                            continue
                        if rfq_id:
                            seen_ids.add(rfq_id)

                        # Build the "link" we surface in the UI. PowerApps doesn't give us a public
                        # per-RFQ page, so we deep-link to the main list with a hash.
                        src_url = f"{LIST_URL}#rfq={rfq_id}" if rfq_id else LIST_URL

                        # Title fallback
                        final_title = title or rfq_id or "City of Columbus RFQ"

                        # We don't have full description text without hitting the popup's _api.
                        # For now we'll just reuse title so we at least capture *something* in full_text.
                        desc_text = final_title  # <<< added

                        # hash_body for diff detection downstream
                        hash_body_val = _make_hash(
                            rfq_id=rfq_id,
                            dept=dept,
                            title=final_title,
                            typ=typ,
                            due_txt=due_txt,
                        )  # <<< added

                        # Build RawOpportunity with new fields
                        items.append(
                            RawOpportunity(
                                source="city_columbus",
                                source_url=safe_source_url(AGENCY_NAME, src_url, LIST_URL),
                                title=final_title,
                                summary=f"{dept} | {typ}".strip(" |"),
                                description=desc_text,          # <<< added
                                category=typ,
                                agency_name=AGENCY_NAME,
                                location_geo=LOCATION,
                                posted_date=None,               # not present in row
                                due_date=due_dt,
                                prebid_date=None,               # not present in row
                                attachments=None,               # we are not scraping attachments yet
                                status="open",
                                hash_body=hash_body_val,        # <<< added
                                external_id=rfq_id,             # <<< added (Solicitation # / RFQ)
                                keyword_tag=keyword_tag,
                                date_added=datetime.now(timezone.utc),  # 👈 NEW
                            )
                        )
                        added += 1

                    except Exception as e:
                        log.warning("Row parse error: %s", e)
                        _dump_html(driver)
                        _shot(driver, "row_error")

                print(
                    f"Page {page_num}: rows={len(rows)} added={added} "
                    f"total_unique={len(seen_ids)}"
                )

                # Find "Next"
                nxt = _find_next(ctx)
                if not nxt:
                    print("No Next button; stopping pagination.")
                    break

                # Did Next actually change?
                before_first_key = _row_key(rows[0])
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", nxt
                    )
                except Exception:
                    pass
                try:
                    nxt.click()
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", nxt)
                    except Exception:
                        print("Next click failed; stopping.")
                        break

                changed = False
                t_end = time.time() + 4.0
                while time.time() < t_end:
                    time.sleep(0.2)
                    new_rows = _rows(ctx)
                    if new_rows:
                        after_first_key = _row_key(new_rows[0])
                        if after_first_key and after_first_key != before_first_key:
                            changed = True
                            break
                if not changed:
                    print(
                        "Next click did not change rows; stopping pagination to avoid loop."
                    )
                    break

                if page_num >= max_pages:
                    print("Max pages reached; stopping pagination.")
                    break

            # If we successfully scraped from this context, don't bother trying other iframes
            if items:
                break

        if not items:
            _dump_html(driver)
            _shot(driver, "no_items")
            raise TimeoutError(
                "No RFQs parsed; selectors may need a small tweak. Check the HTML dump."
            )

        print(f"Scraped {len(items)} unique RFQs from Columbus.")
        return items

    finally:
        try:
            driver.quit()
        except Exception:
            pass


async def fetch() -> List[RawOpportunity]:
    """Async wrapper to match your ingest framework."""
    return await asyncio.to_thread(fetch_sync)
