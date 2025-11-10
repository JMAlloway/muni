import asyncio
import logging
import re
import secrets
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

try:
    import cloudscraper  # type: ignore
    HAVE_CLOUDSCRAPER = True
except Exception:
    HAVE_CLOUDSCRAPER = False

try:
    from playwright.async_api import async_playwright  # type: ignore
    HAVE_PLAYWRIGHT = True
except Exception:
    HAVE_PLAYWRIGHT = False

try:
    from playwright.sync_api import sync_playwright  # type: ignore
    HAVE_PLAYWRIGHT_SYNC = True
except Exception:
    HAVE_PLAYWRIGHT_SYNC = False

logger = logging.getLogger("columbus")

BASE = "https://ohiobuys.ohio.gov"
ACCESS_CHECK_URL = BASE + "/page.aspx/en/bas/access_check"
BROWSE_URL = BASE + "/page.aspx/en/rfp/request_browse_public"

# --- regexes for final browse page parsing ---

ROW_ID_PATTERN = re.compile(
    r"__ivHtmlControls\['body_x_grid_grd_tr_(\d+)_", re.IGNORECASE
)

CELL_PATTERN = re.compile(
    r"__ivHtmlControls\['body_x_grid_grd_tr_(?P<rowid>\d+)[^']*?_(?P<ctl>ctl\d+)'\]\s*=\s*\"(?P<html>.*?)\";",
    re.IGNORECASE | re.DOTALL,
)

CAPTCHA_TABLE_JS_PATTERN = re.compile(
    r"\$\('#body_x_prxCaptcha_x_divCaptcha'\)\.html\('(?P<html>.*?)'\);",
    re.DOTALL,
)

HREF_PATTERN = re.compile(r'href="([^"]+)"', re.IGNORECASE)
TAG_STRIP_PATTERN = re.compile(r"<.*?>", re.DOTALL)


# ------------------------
# helpers: text cleaning, date parsing
# ------------------------

def _clean_html_to_text(fragment: str) -> str:
    """
    Take the HTML snippet stored in __ivHtmlControls[...] (which uses escaped sequences like \u003c),
    unescape it, strip tags, and trim.
    """
    frag = fragment.encode("utf-8").decode("unicode_escape")
    frag = TAG_STRIP_PATTERN.sub("", frag)
    return frag.strip()


def _parse_due_date(txt: str) -> Optional[datetime]:
    """
    Try multiple formats. Returns a naive datetime or None.
    """
    raw = (txt or "").strip()
    if not raw or raw.upper() == "TBD":
        return None

    fmts = [
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    return None


# ------------------------
# HTTP session helpers / Cloudflare handling
# ------------------------

def _default_headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", ";Not A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


def _create_http_session(force_cloudscraper: Optional[bool] = None):
    """
    Create a session that looks like Chrome. Prefer cloudscraper when available
    to better handle Cloudflare-managed challenges.
    """
    use_cloudscraper = force_cloudscraper
    if use_cloudscraper is None:
        env_flag = os.getenv("OHIOBUYS_USE_CLOUDSCRAPER", "").strip().lower()
        use_cloudscraper = env_flag in ("1", "true", "yes", "on")

    session = None
    if HAVE_CLOUDSCRAPER:
        try:
            session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
        except Exception as e:
            logger.warning(f"Cloudscraper failed to initialize: {e}")
            session = requests.Session()
    else:
        session = requests.Session()

    session.headers.update(_default_headers())
    return session


def _apply_cookie_string(session: requests.Session, cookie_str: str, domain: str = "ohiobuys.ohio.gov") -> None:
    """
    Accept a browser-style cookie string (e.g., copied from devtools) and apply it
    to the session for the target domain.
    """
    for part in cookie_str.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            session.cookies.set(name, value, domain=domain)


def _is_cloudflare_block(status_code: int, text: str, headers: Dict[str, str]) -> bool:
    if status_code in (403, 429, 503):
        return True
    h_lower = {k.lower(): v for k, v in headers.items()}
    server_val = h_lower.get("server", "").lower()
    if "cloudflare" in server_val:
        snippet = (text or "")[:2000].lower()
        tokens = [
            "cloudflare",
            "attention required",
            "verify you are human",
            "cf-error",
            "ray id",
        ]
        return any(t in snippet for t in tokens)
    return False


# ------------------------
# IMPROVED CAPTCHA DECODER with Fuzzy Matching
# ------------------------

def _bitmap_signature(bmp: List[str]) -> str:
    """
    Normalize a bitmap into a canonical multi-line signature:
    - left-trim by the minimal common leading spaces across rows
    - strip trailing whitespace on each row
    - join rows with '\n'
    - trim leading/trailing newlines
    """
    leading_counts: List[int] = []
    for line in bmp:
        if line.strip():
            leading_counts.append(len(line) - len(line.lstrip(" ")))
    min_lead = min(leading_counts) if leading_counts else 0
    norm_lines = [line[min_lead:].rstrip() for line in bmp]
    return "\n".join(norm_lines).strip("\n")


def _hamming_distance(sig1: str, sig2: str) -> int:
    """
    Calculate character-level Hamming distance between two signature strings.
    Handles different lengths by padding with spaces.
    """
    max_len = max(len(sig1), len(sig2))
    s1 = sig1.ljust(max_len)
    s2 = sig2.ljust(max_len)
    return sum(c1 != c2 for c1, c2 in zip(s1, s2))


def _get_known_character_signatures() -> Dict[str, str]:
    """
    Returns all known character bitmap signatures.
    Each signature is normalized (left-trimmed, trailing spaces removed).
    """
    sigs = {}

    # Numbers
    sigs["0"] = _bitmap_signature([
        " *****",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        " *****",
    ])

    sigs["1"] = _bitmap_signature([
        "   *",
        "  **",
        " * *",
        "   *",
        "   *",
        "   *",
        "*******",
    ])

    sigs["1_alt"] = _bitmap_signature([
        "*******",
        "   *",
        "   *",
        "   *",
        "   *",
        "   *",
        "   *",
    ])

    sigs["4"] = _bitmap_signature([
        "    *",
        "   **",
        "  * *",
        " *  *",
        "*******",
        "    *",
        "    *",
    ])

    sigs["7"] = _bitmap_signature([
        "*******",
        "     *",
        "    *",
        "   *",
        "  *",
        " *",
        "*******",
    ])

    sigs["7_alt"] = _bitmap_signature([
        "*******",
        "     *",
        "    *",
        "   *",
        "  *",
        " *",
        "*",
    ])

    sigs["8"] = _bitmap_signature([
        " *****",
        "*     *",
        "*     *",
        " *****",
        "*     *",
        "*     *",
        " *****",
    ])

    sigs["8_alt"] = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "******",
        "*     *",
        "*     *",
        "******",
    ])

    # Letters
    sigs["A"] = _bitmap_signature([
        "   *",
        "  * *",
        "  * *",
        " *   *",
        " *****",
        "*     *",
        "*     *",
    ])

    sigs["C"] = _bitmap_signature([
        " *****",
        "*     *",
        "*",
        "*",
        "*",
        "*     *",
        " *****",
    ])

    sigs["D"] = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "******",
    ])

    sigs["E"] = _bitmap_signature([
        "*******",
        "*",
        "*",
        "****",
        "*",
        "*",
        "*******",
    ])

    sigs["G"] = _bitmap_signature([
        " *****",
        "*     *",
        "*",
        "*",
        "*   ***",
        "*     *",
        " *****",
    ])

    sigs["G_alt1"] = _bitmap_signature([
        " *****",
        "*     *",
        "      *",
        "    **",
        "      *",
        "*     *",
        " *****",
    ])

    sigs["G_alt2"] = _bitmap_signature([
        " *****",
        "*     *",
        "      *",
        "     **",
        "      *",
        "*     *",
        " *****",
    ])

    sigs["H"] = _bitmap_signature([
        "*     *",
        "*     *",
        "*     *",
        "*******",
        "*     *",
        "*     *",
        "*     *",
    ])

    sigs["I"] = _bitmap_signature([
        "*******",
        "   *",
        "   *",
        "   *",
        "   *",
        "   *",
        "*******",
    ])

    sigs["J"] = _bitmap_signature([
        "      *",
        "      *",
        "      *",
        "      *",
        "      *",
        "*     *",
        " *****",
    ])

    sigs["L"] = _bitmap_signature([
        "*",
        "*",
        "*",
        "*",
        "*",
        "*",
        "*******",
    ])

    sigs["M"] = _bitmap_signature([
        "*     *",
        "**   **",
        "* * * *",
        "*  *  *",
        "*     *",
        "*     *",
        "*     *",
    ])

    sigs["O"] = _bitmap_signature([
        " *****",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        " *****",
    ])

    sigs["P"] = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "******",
        "*",
        "*",
        "*",
    ])

    sigs["R"] = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "******",
        "*   *",
        "*    *",
        "*     *",
    ])

    sigs["U"] = _bitmap_signature([
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        " *****",
    ])

    sigs["W"] = _bitmap_signature([
        "*     *",
        "*     *",
        "*     *",
        "*  *  *",
        "* * * *",
        "**   **",
        "*     *",
    ])

    sigs["X"] = _bitmap_signature([
        "*     *",
        "**    *",
        "* *   *",
        "*  *  *",
        "*   * *",
        "*    **",
        "*     *",
    ])

    sigs["X_alt1"] = _bitmap_signature([
        "*     *",
        " *   *",
        "  * *",
        "   *",
        "  * *",
        " *   *",
        "*     *",
    ])

    sigs["X_alt2"] = _bitmap_signature([
        "  ***",
        " *   *",
        "*   * *",
        "*  *  *",
        "* *   *",
        " *   *",
        "  ***",
    ])

    sigs["Y"] = _bitmap_signature([
        "*     *",
        " *   *",
        "  * *",
        "   *",
        "   *",
        "   *",
        "   *",
    ])

    sigs["Y_alt"] = _bitmap_signature([
        "*     *",
        "*     *",
        "  *   *",
        "  *   *",
        "   * *",
        "   * *",
        "    *",
    ])

    # Build reverse map: signature -> character
    sig_to_char = {}
    for char, sig in sigs.items():
        # Remove variant suffixes (_alt, _alt1, etc.)
        base_char = char.split("_")[0]
        sig_to_char[sig] = base_char

    return sig_to_char


def _fuzzy_match_character(bmp: List[str], threshold: int = 15) -> Tuple[str, int]:
    """
    Match a character bitmap using fuzzy matching (Hamming distance).
    Returns (character, confidence_score) where lower score = better match.
    Returns ("?", 999) if no good match found.
    """
    sig = _bitmap_signature(bmp)
    known_sigs = _get_known_character_signatures()

    best_char = "?"
    best_distance = 999

    for known_sig, char in known_sigs.items():
        distance = _hamming_distance(sig, known_sig)
        if distance < best_distance:
            best_distance = distance
            best_char = char

    # If distance is too high, we don't have confidence
    if best_distance > threshold:
        return "?", best_distance

    return best_char, best_distance


def _save_unknown_bitmap(bmp: List[str], captcha_attempt: int) -> None:
    """
    Save unknown character bitmaps to a learning file for future analysis.
    """
    try:
        learn_dir = Path("logs/captcha_learning")
        learn_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = learn_dir / f"unknown_{timestamp}_{captcha_attempt}.txt"

        with open(filename, "w") as f:
            f.write("# Add this to _get_known_character_signatures():\n")
            f.write('sigs["?"] = _bitmap_signature([\n')
            for line in bmp:
                f.write(f'    "{line}",\n')
            f.write("])\n\n")
            f.write("# Raw bitmap:\n")
            for line in bmp:
                f.write(f"{line}\n")

        logger.info(f"Saved unknown bitmap to {filename}")
    except Exception as e:
        logger.warning(f"Failed to save unknown bitmap: {e}")


def _guess_captcha_text_from_bitmaps(char_bitmaps: List[List[str]], attempt: int = 0) -> str:
    """
    Convert each per-character bitmap block into the actual character using fuzzy matching.
    """
    decoded_chars: List[str] = []
    unknown_found = False

    logger.info("=== CAPTCHA CHAR BITMAPS BEGIN ===")
    for idx, bmp in enumerate(char_bitmaps):
        logger.info(f"[CHAR {idx}]")
        for line in bmp:
            logger.info(line)
        logger.info("---")

        char, confidence = _fuzzy_match_character(bmp, threshold=20)

        if char == "?":
            unknown_found = True
            logger.warning(f"[CHAR {idx}] UNKNOWN (distance={confidence})")
            _save_unknown_bitmap(bmp, attempt)
        else:
            logger.info(f"[CHAR {idx}] Matched '{char}' (confidence={confidence})")

        decoded_chars.append(char)

    logger.info("=== CAPTCHA CHAR BITMAPS END ===")

    captcha_text = "".join(decoded_chars)
    logger.info(f"[CAPTCHA DECODED] {captcha_text} (has_unknown={unknown_found})")

    return captcha_text


# ------------------------
# Captcha extraction
# ------------------------

def _collect_form_fields(form_soup: BeautifulSoup) -> Dict[str, str]:
    """
    Scrape ALL <input name="..."> fields from the access_check form as the base payload.
    """
    payload: Dict[str, str] = {}
    for inp in form_soup.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        value = inp.get("value", "")
        payload[name] = value
    return payload


def _extract_captcha_table_html(access_html: str) -> Optional[str]:
    """
    Pull the escaped captcha table HTML from the inline script block.
    """
    m = CAPTCHA_TABLE_JS_PATTERN.search(access_html)
    if not m:
        return None
    return m.group("html")


def _decode_captcha_ascii_blocks(table_html_escaped: str) -> Dict[str, Any]:
    """
    Parse captcha table into character bitmaps.
    """
    html_real = table_html_escaped.encode("utf-8").decode("unicode_escape")

    soup_tbl = BeautifulSoup(html_real, "html.parser")
    rows = soup_tbl.find_all("tr")

    grid: List[List[str]] = []
    for tr in rows:
        row_bits = []
        for td in tr.find_all("td"):
            cell_txt = td.get_text(strip=True)
            row_bits.append("*" if cell_txt == "*" else " ")
        grid.append(row_bits)

    num_rows = len(grid)
    num_cols = len(grid[0]) if num_rows else 0

    col_is_blank = []
    for c in range(num_cols):
        col_vals = [grid[r][c] for r in range(num_rows)]
        col_is_blank.append(all(v == " " for v in col_vals))

    blocks: List[List[int]] = []
    current_block_cols: List[int] = []
    for c in range(num_cols):
        if col_is_blank[c]:
            if current_block_cols:
                blocks.append(current_block_cols)
                current_block_cols = []
        else:
            current_block_cols.append(c)
    if current_block_cols:
        blocks.append(current_block_cols)

    char_bitmaps: List[List[str]] = []
    for block_cols in blocks:
        left = min(block_cols)
        right = max(block_cols)
        bmp_rows: List[str] = []
        for r in range(num_rows):
            row_slice = "".join(grid[r][left:right + 1])
            bmp_rows.append(row_slice)
        char_bitmaps.append(bmp_rows)

    return {
        "bitmap_rows": ["".join(r) for r in grid],
        "char_bitmaps": char_bitmaps,
    }


def _massage_payload_for_submit(payload: Dict[str, str], captcha_text: str) -> Dict[str, str]:
    """
    Adjust the scraped form payload for submission.
    """
    payload["__LASTFOCUS"] = "body_x_prxCaptcha_x_txtCaptcha"
    payload["__EVENTTARGET"] = "proxyActionBar:x:_cmdSave"
    payload["__EVENTARGUMENT"] = ""

    payload.setdefault("REQUEST_METHOD", "GET")
    payload.setdefault("HTTP_RESOLUTION", "")

    for k in list(payload.keys()):
        if "prxCaptcha" in k and k.endswith("txtCaptcha"):
            payload[k] = captcha_text

    payload["header:x:prxHeaderLogInfo:x:ContrastModal:chkContrastTheme_radio"] = "true"
    payload["header:x:prxHeaderLogInfo:x:ContrastModal:chkContrastTheme"] = "True"
    payload.setdefault("header:x:prxHeaderLogInfo:x:ContrastModal:chkPassiveNotification", "0")

    payload.setdefault("proxyActionBar:x:_cmdSave", "")
    payload.setdefault("proxyActionBar:x:txtWflRefuseMessage", "")
    payload.setdefault("hdnMandatory", "0")
    payload.setdefault("hdnWflAction", "")
    payload.setdefault("body:_ctl0", "")

    return payload


# ------------------------
# Playwright fallback
# ------------------------

async def _playwright_get_browse_html() -> Optional[str]:
    """
    Use a real browser (Playwright) to navigate through access_check.
    """
    if not HAVE_PLAYWRIGHT_SYNC and not HAVE_PLAYWRIGHT:
        logger.info("Playwright not available in this environment.")
        return None

    if HAVE_PLAYWRIGHT_SYNC:
        def _run_sync() -> Optional[str]:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=_default_headers().get("User-Agent"),
                        extra_http_headers={
                            k: v for k, v in _default_headers().items() if k.lower() != "user-agent"
                        },
                    )
                    page = context.new_page()
                    page.goto(ACCESS_CHECK_URL, wait_until="domcontentloaded")

                    max_attempts = int(os.getenv("OHIOBUYS_MAX_CAPTCHA_ATTEMPTS", "5") or "5")
                    for attempt in range(max_attempts):
                        access_html = page.content()
                        captcha_html_escaped = _extract_captcha_table_html(access_html)
                        captcha_guess = ""
                        if captcha_html_escaped:
                            decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
                            char_bitmaps = decoded_info["char_bitmaps"]
                            captcha_guess = _guess_captcha_text_from_bitmaps(char_bitmaps, attempt)

                        if captcha_guess and "?" not in captcha_guess:
                            try:
                                page.fill("#body_x_prxCaptcha_x_txtCaptcha", captcha_guess)
                            except Exception:
                                try:
                                    page.evaluate(
                                        "(val) => { const el = document.getElementById('body_x_prxCaptcha_x_txtCaptcha'); if (el) el.value = val; }",
                                        captcha_guess,
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to fill captcha: {e}")

                            for sel in [
                                "#proxyActionBar_x__cmdSave",
                                "[id*='_cmdSave']",
                                "text=Continue",
                                "text=Submit",
                            ]:
                                try:
                                    page.click(sel, timeout=2000)
                                    break
                                except Exception:
                                    continue
                            try:
                                page.wait_for_timeout(1500)
                            except Exception:
                                pass
                            break
                        else:
                            try:
                                page.reload(wait_until="domcontentloaded")
                                page.wait_for_timeout(500)
                            except Exception as e:
                                logger.warning(f"Failed to reload: {e}")

                    page.goto(BROWSE_URL, wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector("[id*='body_x_grid_grd']", timeout=5000)
                    except Exception:
                        pass
                    html = page.content()
                    context.close()
                    browser.close()
                    return html
            except Exception as e:
                logger.warning(f"Playwright fallback failed: {e}")
                return None

        return await asyncio.to_thread(_run_sync)

    return None


# ------------------------
# browse page parsing
# ------------------------

def _parse_rows_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parse opportunities from the browse page HTML.
    """
    row_ids = set(ROW_ID_PATTERN.findall(html))
    buckets: Dict[str, Dict[str, str]] = {}

    for match in CELL_PATTERN.finditer(html):
        rowid = match.group("rowid")
        ctl = match.group("ctl")
        raw_html = match.group("html")
        buckets.setdefault(rowid, {})[ctl] = raw_html

    results: List[Dict[str, Any]] = []

    for rowid in row_ids:
        cells = buckets.get(rowid, {})

        c00 = cells.get("ctl00", "")
        c01 = cells.get("ctl01", "")
        c02 = cells.get("ctl02", "")
        c03 = cells.get("ctl03", "")
        c04 = cells.get("ctl04", "")
        c05 = cells.get("ctl05", "")

        solicitation_text = _clean_html_to_text(c00)
        if (
            not solicitation_text
            or solicitation_text.startswith("*")
            or "Solicitation" in solicitation_text
        ):
            continue

        href_match = HREF_PATTERN.search(c00)
        if href_match:
            href = href_match.group(1)
            if href.startswith("http"):
                full_link = href
            else:
                full_link = urljoin(BASE + "/", href.lstrip("/"))
        else:
            full_link = BROWSE_URL

        title_text = _clean_html_to_text(c01)
        agency_text = _clean_html_to_text(c02)
        due_text = _clean_html_to_text(c03)
        type_text = _clean_html_to_text(c04)
        status_text = _clean_html_to_text(c05)

        due_dt = _parse_due_date(due_text)

        results.append(
            {
                "external_id": solicitation_text,
                "title": title_text,
                "agency_name": agency_text,
                "due_date": due_dt,
                "posted_date": None,
                "status": status_text or "Open",
                "category": type_text or "RFP/RFQ",
                "source_url": full_link,
                "attachments": [],
                "summary": "",
                "full_text": "",
                "source": "OhioBuys",
                "keyword_tag": None,
                "location_geo": "",
                "prebid_date": None,
                "date_added": datetime.now(timezone.utc),
            }
        )

    return results


# ------------------------
# main entrypoint
# ------------------------

async def fetch() -> List[Dict[str, Any]]:
    """
    Main scraping function with improved captcha handling.
    """
    logger.info("Starting OhioBuys scrape (improved captcha solver)...")

    session = _create_http_session()
    cookie_str = os.getenv("OHIOBUYS_COOKIES", "").strip()
    if cookie_str:
        _apply_cookie_string(session, cookie_str)
        logger.info("Applied cookies from OHIOBUYS_COOKIES env var.")

    r_get = session.get(ACCESS_CHECK_URL)
    if r_get.status_code != 200:
        logger.error(f"access_check GET failed: {r_get.status_code}")
        return []

    if _is_cloudflare_block(r_get.status_code, r_get.text, dict(r_get.headers)):
        logger.warning("Detected Cloudflare challenge. Trying cloudscraper...")
        if HAVE_CLOUDSCRAPER:
            session = _create_http_session(force_cloudscraper=True)
            if cookie_str:
                _apply_cookie_string(session, cookie_str)
            r_get = session.get(ACCESS_CHECK_URL)

        if _is_cloudflare_block(r_get.status_code, r_get.text, dict(r_get.headers)):
            logger.warning("Still blocked. Attempting Playwright fallback...")
            html = await _playwright_get_browse_html()
            if html:
                rows = _parse_rows_from_html(html)
                logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
                return rows
            return []

    access_html = r_get.text
    soup = BeautifulSoup(access_html, "html.parser")

    logger.info(f"[ACCESS_CHECK] Got {len(access_html)} bytes, status={r_get.status_code}")

    max_attempts = int(os.getenv("OHIOBUYS_MAX_CAPTCHA_ATTEMPTS", "10") or "10")
    attempt = 0
    captcha_guess = ""
    solved = False

    while attempt < max_attempts:
        attempt += 1
        logger.info(f"[CAPTCHA ATTEMPT {attempt}/{max_attempts}]")

        raw_payload = _collect_form_fields(soup)

        captcha_html_escaped = _extract_captcha_table_html(access_html)
        if captcha_html_escaped:
            decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
            char_bitmaps = decoded_info["char_bitmaps"]
            captcha_guess = _guess_captcha_text_from_bitmaps(char_bitmaps, attempt)
        else:
            logger.warning("Could not locate captcha table in HTML")
            captcha_guess = ""

        # With fuzzy matching, we accept captchas with low-confidence matches
        # Only retry if we have "?" (completely unknown characters)
        if captcha_guess and "?" not in captcha_guess:
            logger.info(f"✓ Captcha decoded successfully: '{captcha_guess}'")
            solved = True
            break
        else:
            logger.warning(f"✗ Captcha has unknown characters: '{captcha_guess}'")
            logger.info("Refreshing page to get new captcha...")
            r_get = session.get(ACCESS_CHECK_URL)
            if r_get.status_code == 200:
                access_html = r_get.text
                soup = BeautifulSoup(access_html, "html.parser")
            else:
                logger.error("Failed to refresh access_check page")
                break

    if not solved:
        logger.error("Failed to solve captcha after all attempts. Trying Playwright...")
        html = await _playwright_get_browse_html()
        if html:
            rows = _parse_rows_from_html(html)
            logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
            return rows
        return []

    payload = _massage_payload_for_submit(raw_payload, captcha_guess)

    post_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE,
        "Referer": ACCESS_CHECK_URL,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }

    logger.info(f"[SUBMIT] Posting captcha: '{captcha_guess}'")
    r_post = session.post(
        ACCESS_CHECK_URL,
        data=payload,
        headers=post_headers,
        allow_redirects=True,
    )

    logger.info(f"[POST] status={r_post.status_code}, final_url={r_post.url}")

    r_browse = session.get(BROWSE_URL, allow_redirects=True)
    logger.info(f"[BROWSE] status={r_browse.status_code}, url={r_browse.url}")

    if r_browse.status_code != 200:
        logger.error(f"Browse page failed with status {r_browse.status_code}")
        return []

    # Check if we got redirected back to access_check (captcha was wrong)
    if "access_check" in r_browse.url.lower():
        logger.error("Got redirected back to access_check - captcha was likely wrong!")
        logger.info("Response snippet: " + r_browse.text[:1000])
        return []

    rows = _parse_rows_from_html(r_browse.text)
    logger.info(f"✓ OhioBuys: successfully scraped {len(rows)} opportunities")

    return rows


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(fetch())
    print(f"\n{'='*60}")
    print(f"Scraped {len(results)} opportunities")
    print(f"{'='*60}")
    if results:
        print(f"\nFirst opportunity:")
        print(json.dumps(results[0], indent=2, default=str))
