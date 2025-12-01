# app/ingest/municipalities/city_columbus.py
import os
import time
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Iterator, Dict, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver

from app.ingest.utils import safe_source_url
from app.ingest.base import RawOpportunity

# Optional: undetected_chromedriver; we default to plain Selenium for stability
try:
    import undetected_chromedriver as uc  # type: ignore

    _HAS_UC = True
except Exception:
    _HAS_UC = False
    from selenium import webdriver  # type: ignore
    # ChromeService + ChromeDriverManager imported inside fallback branch


# ------------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------------
LIST_URL = "https://columbusvendorservices.powerappsportals.com/OpenRFQs/"
AGENCY_NAME = "City of Columbus"
LOCATION = "Franklin County, OH"

HEADFUL_DEBUG = False  # show browser while stabilizing; set False in prod
FORCE_SELENIUM = True  # keep True for reliability on this portal; flip False if you want UC
ENABLE_MODAL_EXTRACTION = True  # Set False to skip detail-page scrape
DEBUG_LIMIT_MODALS: Optional[int] = None  # e.g. 3 to only scrape details for first N rows

PAGE_TIMEOUT_S = 60
WAIT_TIMEOUT_S = 15
GLOBAL_HARD_STOP_S = 90

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".", ".", "."))
HTML_DUMP = os.path.join(BASE_DIR, "columbus_openrfqs.html")
SHOT_DIR = os.path.join(BASE_DIR, "debug_shots")
os.makedirs(SHOT_DIR, exist_ok=True)

# Offline skeleton text can use straight or curly apostrophe
OFFLINE_MARKERS = [
    "You're offline. This is a read only version of the page.",
    "You’re offline. This is a read only version of the page.",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [columbus] %(levelname)s: %(message)s",
)
log = logging.getLogger("columbus")


# ------------------------------------------------------------------------------------
# Helpers: classification / dates
# ------------------------------------------------------------------------------------
def _classify_keyword_tag(title: str, dept: str, typ: str) -> str:
    """
    Very dumb keyword pass for now. You can expand this list over time.
    We'll look at title + dept + typ all lowercased.
    """
    blob = f"{title} {dept} {typ}".lower()

    KEYWORDS = [
        ("hvac", "HVAC"),
        ("air handler", "HVAC"),
        ("rooftop unit", "HVAC"),
        ("chiller", "HVAC"),
        ("boiler", "HVAC"),
        ("electrical", "Electrical"),
        ("lighting", "Electrical"),
        ("led retrofit", "Electrical"),
        ("generator", "Electrical"),
        ("plumbing", "Plumbing"),
        ("sewer", "Plumbing"),
        ("storm sewer", "Plumbing"),
        ("sanitary", "Plumbing"),
        ("water line", "Plumbing"),
        ("hydrant", "Plumbing"),
        ("asphalt", "Paving / Asphalt"),
        ("paving", "Paving / Asphalt"),
        ("resurface", "Paving / Asphalt"),
        ("mill & fill", "Paving / Asphalt"),
        ("concrete", "Paving / Asphalt"),
        ("mowing", "Landscaping / Grounds"),
        ("landscap", "Landscaping / Grounds"),
        ("turf", "Landscaping / Grounds"),
        ("tree removal", "Landscaping / Grounds"),
        ("snow removal", "Landscaping / Grounds"),
        ("salt", "Landscaping / Grounds"),
        ("network", "IT / Networking"),
        ("firewall", "IT / Networking"),
        ("server", "IT / Networking"),
        ("switches", "IT / Networking"),
        ("camera", "Security / Cameras"),
        ("surveillance", "Security / Cameras"),
        ("police vehicle", "Vehicles / Fleet"),
        ("patrol vehicle", "Vehicles / Fleet"),
        ("pickup truck", "Vehicles / Fleet"),
        ("dump truck", "Vehicles / Fleet"),
        ("uniform", "Uniforms / Apparel"),
        ("janitorial", "Janitorial / Cleaning"),
        ("cleaning", "Janitorial / Cleaning"),
        ("supplies", "General Supplies"),
        ("office", "General Supplies"),
        ("print", "Printing / Signage"),
        ("signage", "Printing / Signage"),
        ("banner", "Printing / Signage"),
        ("foam board", "Printing / Signage"),
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
    """Lightweight screenshot helper used only on hard failures."""
    try:
        p = os.path.join(SHOT_DIR, f"{int(time.time())}_{name}.png")
        driver.save_screenshot(p)
        log.info("Saved screenshot: %s", p)
    except Exception:
        pass


def _dump_html(driver: WebDriver) -> None:
    """Dump current page HTML to a single known file (for debugging)."""
    try:
        with open(HTML_DUMP, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        log.info("Dumped HTML: %s", HTML_DUMP)
    except Exception:
        pass


# ------------------------------------------------------------------------------------
# WebDriver setup
# ------------------------------------------------------------------------------------
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
        from selenium import webdriver  # type: ignore
        from selenium.webdriver.chrome.service import Service as ChromeService  # type: ignore
        from webdriver_manager.chrome import ChromeDriverManager  # type: ignore

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


# ------------------------------------------------------------------------------------
# DOM helpers
# ------------------------------------------------------------------------------------
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
        (
            By.CSS_SELECTOR,
            "#OpenRFQs_next:not(.disabled) a, #OpenRFQs_next:not(.disabled)",
        ),
        (By.CSS_SELECTOR, ".dataTables_paginate .next:not(.disabled) a"),
        (By.CSS_SELECTOR, "li.next:not(.disabled) a, li.pagination-next:not(.disabled) a"),
        (
            By.XPATH,
            "//a[contains(., 'Next') and not(contains(@aria-disabled,'true'))]",
        ),
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


def _get_field_by_id(driver: WebDriver, element_id: str) -> str:
    """
    Extract field value by ID on the *detail page*.
    """
    try:
        element = driver.find_element(By.ID, element_id)
        return element.text.strip()
    except Exception:
        return ""


def _empty_detail_result() -> Dict[str, Any]:
    return {
        "description": "",
        "attachments": [],
        "delivery_date": None,
        "delivery_name": "",
        "delivery_address": "",
        "solicitation_type": "",
        "line_items": [],
    }


# ------------------------------------------------------------------------------------
# Detail page extraction
# ------------------------------------------------------------------------------------
def _extract_detail_panel_data(driver: WebDriver, wait: WebDriverWait) -> Dict[str, Any]:
    """
    Extract data from the Columbus *detail page* that opens after clicking 'View Details'.
    We assume the detail page uses stable IDs like:
      - description
      - SolicitationType
      - delivery (date)
      - deliveryname
      - deliveryaddress
      - AttachmentTable
      - RfqLineTable
    """
    result = _empty_detail_result()

    try:
        # Check for offline skeleton mode
        if any(m in driver.page_source for m in OFFLINE_MARKERS):
            log.error("Offline skeleton detected on detail page – no RFQ data available")
            return result

        log.info("Waiting for detail page content (description/deliveryname)...")
        try:
            wait.until(
                lambda d: _get_field_by_id(d, "description")
                or _get_field_by_id(d, "deliveryname")
            )
            log.info("Detail page content detected!")
        except Exception as e:
            log.warning(f"Timed out waiting for detail page to populate: {e}")
            # continue anyway; maybe some fields are available

        # Small extra wait for async content
        time.sleep(1.0)

        # General / header details
        result["solicitation_type"] = _get_field_by_id(driver, "SolicitationType")
        log.info(f"Solicitation Type: '{result['solicitation_type']}'")

        delivery_date_text = _get_field_by_id(driver, "delivery")
        if delivery_date_text:
            result["delivery_date"] = _parse_date(delivery_date_text)
            log.info(f"Delivery Date: '{delivery_date_text}'")

        result["delivery_name"] = _get_field_by_id(driver, "deliveryname")
        result["delivery_address"] = _get_field_by_id(driver, "deliveryaddress")

        # Description
        result["description"] = _get_field_by_id(driver, "description")
        log.info(f"Found description, length: {len(result['description'])}")

        # Attachments from table with id="AttachmentTable"
        try:
            attachments_table = driver.find_element(By.ID, "AttachmentTable")
            attachment_rows = attachments_table.find_elements(By.CSS_SELECTOR, "tbody tr")
            log.info(f"Found {len(attachment_rows)} attachment row(s)")
            for row in attachment_rows:
                try:
                    cells = row.find_elements(By.CSS_SELECTOR, "td")
                    if not cells or len(cells) < 2:
                        continue
                    file_name = cells[0].text.strip()
                    link_el = cells[-1].find_element(By.TAG_NAME, "a")
                    url = link_el.get_attribute("href")
                    if url:
                        result["attachments"].append(url)
                        log.info(
                            f"Added attachment: {file_name} -> {url[:80]}..."
                        )
                except Exception as e:
                    log.warning(f"Failed to extract attachment row: {e}")
        except Exception as e:
            log.info(f"No Attachments table found (this is OK): {e}")

        # Line Details from table with id="RfqLineTable"
        try:
            line_table = driver.find_element(By.ID, "RfqLineTable")

            header_cells = line_table.find_elements(By.CSS_SELECTOR, "thead th")
            headers: List[str] = []
            for h in header_cells:
                txt = (h.text or "").strip()
                if not txt:
                    # sometimes labels live in aria-label/title/data-title
                    txt = (
                        h.get_attribute("aria-label")
                        or h.get_attribute("title")
                        or h.get_attribute("data-title")
                        or ""
                    ).strip()
                headers.append(txt)

            log.info(f"Line Details headers: {headers}")

            for row in line_table.find_elements(By.CSS_SELECTOR, "tbody tr"):
                cells = row.find_elements(By.CSS_SELECTOR, "td")
                if not cells:
                    continue
                data: Dict[str, str] = {}
                for i in range(min(len(headers), len(cells))):
                    key = headers[i] or f"col_{i}"
                    data[key] = (cells[i].text or "").strip()
                result["line_items"].append(data)

            log.info(f"Found {len(result['line_items'])} line items")
        except Exception as e:
            log.info(f"No Line Details table found (this is OK): {e}")

    except Exception as e:
        log.error(f"Detail page extraction error: {e}", exc_info=True)

    log.info(
        "Returning detail data: desc_len=%s, attachments=%s",
        len(result["description"]),
        len(result["attachments"]),
    )
    return result


def _click_row_and_extract_modal(
    driver: WebDriver, wait: WebDriverWait, row_element
) -> Dict[str, Any]:
    """
    For a given row in the OpenRFQs table:
      1. Find the 'View Details' link in that row.
      2. Open it in a new tab.
      3. Scrape the detail page.
      4. Close the tab and return to the listing.
    Returns extracted detail data dict.
    """
    default = _empty_detail_result()

    try:
        log.info("Attempting to open detail page from row...")

        # Try to find a 'View Details' link inside the row
        link = None
        try:
            link = row_element.find_element(
                By.XPATH,
                ".//a[contains(translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view details')]",
            )
        except Exception:
            # Fallback: last <a> in the row
            try:
                links = row_element.find_elements(By.TAG_NAME, "a")
                if links:
                    link = links[-1]
            except Exception:
                link = None

        if not link:
            log.warning("No detail link found in row; skipping detail extraction")
            return default

        href = link.get_attribute("href")
        if not href:
            log.warning("Detail link has no href; skipping detail extraction")
            return default

        original_window = driver.current_window_handle
        existing_handles = set(driver.window_handles)

        # Open detail page in new tab
        driver.execute_script("window.open(arguments[0], '_blank');", href)

        # Wait for new tab
        def _new_handle(d: WebDriver):
            handles = set(d.window_handles)
            diff = handles - existing_handles
            return list(diff)[0] if diff else None

        new_handle = WebDriverWait(driver, WAIT_TIMEOUT_S).until(_new_handle)
        driver.switch_to.window(new_handle)

        # Now we're on the detail page
        detail_data = _extract_detail_panel_data(driver, wait)

        # Close detail tab and go back to listing
        driver.close()
        driver.switch_to.window(original_window)

        return detail_data

    except Exception as e:
        log.error(f"Failed to open/scrape detail page: {e}", exc_info=True)
        # Try to recover to main window
        try:
            if len(driver.window_handles) >= 1:
                driver.switch_to.window(driver.window_handles[0])
        except Exception:
            pass
        return default


# ------------------------------------------------------------------------------------
# Main scraper
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
            raise TimeoutError(
                "OpenRFQs table did not appear within the hard time limit."
            )

    try:
        log.info("Navigating to %s", LIST_URL)
        driver.get(LIST_URL)
        time.sleep(1.0)

        # Check for offline skeleton mode
        if any(m in driver.page_source for m in OFFLINE_MARKERS):
            _dump_html(driver)
            _shot(driver, "offline_skeleton")
            raise RuntimeError(
                "Offline skeleton detected – not authenticated or network issue."
            )

        # FIRST PAGE: robust polling for rows
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
                for row_idx, r in enumerate(rows):
                    try:
                        tds = r.find_elements(By.TAG_NAME, "td")
                        if len(tds) < 5:
                            continue

                        # Column map:
                        # [0] = RFQ number / Solicitation #
                        # [1] = Department
                        # [2] = Title
                        # [3] = Type (Construction / Goods / etc.)
                        # [4] = Expiry / Due (cell has data-order = epoch seconds)
                        rfq_id = (tds[0].text or "").strip()
                        dept = (tds[1].text or "").strip()
                        title = (tds[2].text or "").strip()
                        typ = (tds[3].text or "").strip()

                        due_cell = tds[4]
                        due_txt = (due_cell.text or "").strip()
                        due_ord = due_cell.get_attribute("data-order") or ""
                        due_dt = _parse_epoch_attr(due_ord) or _parse_date(due_txt)
                        keyword_tag = _classify_keyword_tag(title, dept, typ)

                        # skip duplicates across pagination
                        if rfq_id and rfq_id in seen_ids:
                            continue
                        if rfq_id:
                            seen_ids.add(rfq_id)

                        # Decide whether to hit detail page
                        should_extract_modal = ENABLE_MODAL_EXTRACTION
                        if DEBUG_LIMIT_MODALS is not None:
                            total_processed = len(seen_ids) - 1
                            should_extract_modal = (
                                should_extract_modal
                                and total_processed < DEBUG_LIMIT_MODALS
                            )

                        if should_extract_modal:
                            modal_data = _click_row_and_extract_modal(
                                driver, wait, r
                            )
                        else:
                            if (
                                DEBUG_LIMIT_MODALS is not None
                                and len(seen_ids) - 1 >= DEBUG_LIMIT_MODALS
                            ):
                                log.info(
                                    "Skipping detail extraction "
                                    f"(debug limit reached: {DEBUG_LIMIT_MODALS})"
                                )
                            else:
                                log.info(
                                    "Detail extraction disabled - using table data only"
                                )
                            modal_data = _empty_detail_result()

                        # Build the "link" we surface in the UI.
                        src_url = (
                            f"{LIST_URL}#rfq={rfq_id}" if rfq_id else LIST_URL
                        )

                        # Title fallback
                        final_title = title or rfq_id or "City of Columbus RFQ"

                        # Use full description from detail page if available
                        desc_text = modal_data["description"] or final_title

                        # Add line items to description if available
                        if modal_data["line_items"]:
                            line_items_text = "\n\n### Line Items:\n"
                            for idx, item in enumerate(
                                modal_data["line_items"], 1
                            ):
                                line_items_text += f"\n{idx}. "
                                line_items_text += " | ".join(
                                    f"{k}: {v}" for k, v in item.items() if v
                                )
                            desc_text = desc_text + line_items_text

                        # Use solicitation type from detail if available, otherwise table type
                        final_type = modal_data["solicitation_type"] or typ

                        # Build enhanced summary with delivery info
                        summary_parts = [dept, final_type]
                        if modal_data["delivery_name"]:
                            summary_parts.append(
                                f"Delivery: {modal_data['delivery_name']}"
                            )
                        if modal_data["line_items"]:
                            summary_parts.append(
                                f"{len(modal_data['line_items'])} line items"
                            )
                        summary_text = " | ".join(
                            p for p in summary_parts if p
                        )

                        # hash_body for diff detection downstream
                        hash_body_val = _make_hash(
                            rfq_id=rfq_id,
                            dept=dept,
                            title=final_title,
                            typ=final_type,
                            due_txt=due_txt,
                        )

                        # Build RawOpportunity with enhanced data from detail page
                        items.append(
                            RawOpportunity(
                                source="city_columbus",
                                source_url=safe_source_url(
                                    AGENCY_NAME, src_url, LIST_URL
                                ),
                                title=final_title,
                                summary=summary_text,
                                description=desc_text,
                                category=final_type,
                                agency_name=AGENCY_NAME,
                                location_geo=modal_data["delivery_address"]
                                or LOCATION,
                                posted_date=None,  # not present
                                due_date=due_dt,
                                prebid_date=modal_data[
                                    "delivery_date"
                                ],  # using delivery date as placeholder
                                attachments=(
                                    modal_data["attachments"]
                                    if modal_data["attachments"]
                                    else None
                                ),
                                status="open",
                                hash_body=hash_body_val,
                                external_id=rfq_id,
                                keyword_tag=keyword_tag,
                                date_added=datetime.now(timezone.utc),
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
                        if (
                            after_first_key
                            and after_first_key != before_first_key
                        ):
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

            # If we successfully scraped from this context, don't bother other iframes
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


# ------------------------------------------------------------------------------------
# Async wrapper
# ------------------------------------------------------------------------------------
async def fetch() -> List[RawOpportunity]:
    """Async wrapper to match your ingest framework."""
    return await asyncio.to_thread(fetch_sync)


if __name__ == "__main__":
    # Standalone test mode
    results = fetch_sync()
    print(f"Fetched {len(results)} opportunities.")
