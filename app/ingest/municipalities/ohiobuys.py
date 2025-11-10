import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
import datetime
from datetime import datetime, timezone
import os
import sys
import platform


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

# Each row has an internal numeric row id. We key off 'body_x_grid_grd_tr_<ROWID>_'.
# Be tolerant to grid id variations; only rely on the trailing 'tr_<ROWID>_' part
ROW_ID_PATTERN = re.compile(
    r"__ivHtmlControls\['[^']*tr_(\d+)_", re.IGNORECASE
)

# Each cell for that row shows up in a JS assignment like:
# __ivHtmlControls['body_x_grid_grd_tr_48362_xxx_ctl00'] = "<a ...>SRC00000123</a>";
# ctl00 = solicitation/link, ctl01 = title, ctl02 = agency, ctl03 = due, ctl04 = type, ctl05 = status
CELL_PATTERN = re.compile(
    r"__ivHtmlControls\['[^']*tr_(?P<rowid>\d+)[^']*?_(?P<ctl>ctl\d+)'\]\s*=\s*\"(?P<html>.*?)\";",
    re.IGNORECASE | re.DOTALL,
)

# When we first hit /bas/access_check, the captcha is injected via JS like:
# $('#body_x_prxCaptcha_x_divCaptcha').html('<table>...lots of <td>*</td>...</table>');
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
            if use_cloudscraper:
                session = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows", "mobile": False}
                )
            else:
                # Even if not forced, cloudscraper behaves like requests.Session()
                session = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows", "mobile": False}
                )
        except Exception:
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
        # Heuristic: look for common Cloudflare interstitial content
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
# Playwright fallback
# ------------------------

def _cookies_for_playwright(session: requests.Session) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for c in session.cookies:
        dom = (c.domain or "").lstrip(".")
        if not dom or "ohiobuys.ohio.gov" not in dom:
            continue
        items.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": dom,
                "path": c.path or "/",
                "httpOnly": False,
                "secure": bool(getattr(c, "secure", False)),
                "sameSite": "Lax",
            }
        )
    return items


async def _playwright_get_browse_html(session: Optional[requests.Session] = None) -> Optional[str]:
    """
    Use a real browser (Playwright) to navigate through access_check, solve the
    ASCII captcha using our existing decoders, and then open the browse page.
    Returns the final HTML of the browse page or None on failure.
    """
    if not HAVE_PLAYWRIGHT:
        logger.info("Playwright not available in this environment.")
        return None

    # Prefer sync Playwright via a background thread to avoid Windows asyncio subprocess limitations.
    if HAVE_PLAYWRIGHT_SYNC:
        def _run_sync() -> Optional[str]:
            try:
                # Ensure Windows Proactor event loop so subprocess works
                try:
                    if sys.platform == "win32":
                        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=_default_headers().get("User-Agent"),
                        extra_http_headers={
                            k: v for k, v in _default_headers().items() if k.lower() != "user-agent"
                        },
                    )
                    try:
                        if session is not None:
                            context.add_cookies(_cookies_for_playwright(session))
                    except Exception:
                        pass
                    page = context.new_page()
                    page.goto(ACCESS_CHECK_URL, wait_until="domcontentloaded")

                    max_attempts = int(os.getenv("OHIOBUYS_MAX_CAPTCHA_ATTEMPTS", "5") or "5")
                    for _ in range(max_attempts):
                        access_html = page.content()
                        captcha_html_escaped = _extract_captcha_table_html(access_html)
                        captcha_guess = ""
                        if captcha_html_escaped:
                            decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
                            char_bitmaps = decoded_info["char_bitmaps"]
                            captcha_guess = _guess_captcha_text_from_bitmaps(char_bitmaps)

                        if captcha_guess and "?" not in captcha_guess:
                            try:
                                page.fill("#body_x_prxCaptcha_x_txtCaptcha", captcha_guess)
                            except Exception:
                                try:
                                    page.evaluate(
                                        "(val) => { const el = document.getElementById('body_x_prxCaptcha_x_txtCaptcha'); if (el) el.value = val; }",
                                        captcha_guess,
                                    )
                                except Exception:
                                    pass
                            # Try to submit
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
                            except Exception:
                                pass

                    page.goto(BROWSE_URL, wait_until="domcontentloaded")
                    # Try to trigger the grid population (Search/Apply/Refresh)
                    for sel in [
                        "[id*='cmdSearch']",
                        "text=Search",
                        "text=Apply",
                        "[id*='cmdRefresh']",
                    ]:
                        try:
                            page.click(sel, timeout=1500)
                            break
                        except Exception:
                            continue
                    # Wait for either grid container, grid rows, or inline JS to appear
                    for wait_sel in [
                        "[id*='body_x_grid_grd']",
                        "tr[id*='body_x_grid_grd_tr_']",
                        "script:has-text('__ivHtmlControls[')",
                    ]:
                        try:
                            page.wait_for_selector(wait_sel, timeout=4000)
                            break
                        except Exception:
                            continue
                    html = page.content()
                    context.close()
                    browser.close()
                    return html
            except Exception as e:
                logger.info(f"Playwright fallback failed: {e}")
                return None

        return await asyncio.to_thread(_run_sync)
    else:
        # Fall back to async API if sync not available
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=_default_headers().get("User-Agent"),
                    extra_http_headers={
                        k: v for k, v in _default_headers().items() if k.lower() != "user-agent"
                    },
                )
                try:
                    if session is not None:
                        await context.add_cookies(_cookies_for_playwright(session))
                except Exception:
                    pass
                page = await context.new_page()
                await page.goto(ACCESS_CHECK_URL, wait_until="domcontentloaded")
                # simple path without captcha handling if async subprocess unsupported
                await page.goto(BROWSE_URL, wait_until="domcontentloaded")
                # Try to click Search/Apply and wait briefly
                for sel in [
                    "[id*='cmdSearch']",
                    "text=Search",
                    "text=Apply",
                    "[id*='cmdRefresh']",
                ]:
                    try:
                        await page.click(sel, timeout=1500)
                        break
                    except Exception:
                        continue
                try:
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
                html = await page.content()
                await context.close()
                await browser.close()
                return html
        except Exception as e:
            logger.info(f"Playwright fallback failed: {e}")
            return None


# ------------------------
# access_check helpers
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
    Pull the escaped captcha table HTML from the inline script block that looks like:
    $('#body_x_prxCaptcha_x_divCaptcha').html('<table>...</table>');
    Returns that inner '<table>...</table>' string, but still with \u003c escapes.
    """
    m = CAPTCHA_TABLE_JS_PATTERN.search(access_html)
    if not m:
        return None
    return m.group("html")


def _decode_captcha_ascii_blocks(table_html_escaped: str) -> Dict[str, Any]:
    """
    Given the escaped HTML string for the captcha table:
      - unescape it to real HTML
      - parse rows/cols of <td>*</td> data into a grid of '*'/' '
      - split that grid into "character blocks" by looking for blank columns
      - return those per-character bitmaps
    """
    # Turn \u003c into '<', etc.
    html_real = table_html_escaped.encode("utf-8").decode("unicode_escape")

    soup_tbl = BeautifulSoup(html_real, "html.parser")
    rows = soup_tbl.find_all("tr")

    # Build a 2D grid of "*" or " " of shape [num_rows x num_cols]
    grid: List[List[str]] = []
    for tr in rows:
        row_bits = []
        for td in tr.find_all("td"):
            cell_txt = td.get_text(strip=True)
            row_bits.append("*" if cell_txt == "*" else " ")
        grid.append(row_bits)

    num_rows = len(grid)
    num_cols = len(grid[0]) if num_rows else 0

    # Identify which columns are completely blank across all rows
    col_is_blank = []
    for c in range(num_cols):
        col_vals = [grid[r][c] for r in range(num_rows)]
        col_is_blank.append(all(v == " " for v in col_vals))

    # Group consecutive non-blank columns into character blocks,
    # splitting when we hit at least one blank column.
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

    # Extract each block into its own bitmap (list of row strings like "***  *")
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


def _bitmap_signature(bmp: List[str]) -> str:
    """
    Normalize a bitmap into a canonical multi-line signature:
    - left-trim by the minimal common leading spaces across rows
    - strip trailing whitespace on each row
    - join rows with '\n'
    - trim leading/trailing newlines
    """
    # Determine minimal leading spaces among non-empty rows
    leading_counts: List[int] = []
    for line in bmp:
        if line.strip():
            leading_counts.append(len(line) - len(line.lstrip(" ")))
    min_lead = min(leading_counts) if leading_counts else 0
    norm_lines = [line[min_lead:].rstrip() for line in bmp]
    return "\n".join(norm_lines).strip("\n")


def _guess_captcha_text_from_bitmaps(char_bitmaps: List[List[str]]) -> str:
    """
    Convert each per-character bitmap block into the actual character.
    We learned the font from your last run:

    '0':
         " *****"
         "*     *"
         "*"
         "*"
         "*"
         "*     *"
         " *****"

    '8':
         " *****"
         "*     *"
         "*     *"
         " *****"
         "*     *"
         "*     *"
         " *****"

    'X':
         "*     *"
         "**    *"
         "* *   *"
         "*  *  *"
         "*   * *"
         "*    **"
         "*     *"
    """

    # Classic 0/8/X definitions (7 rows height)
    sig_zero = _bitmap_signature([
        " *****",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        " *****",
    ])

    sig_eight = _bitmap_signature([
        " *****",
        "*     *",
        "*     *",
        " *****",
        "*     *",
        "*     *",
        " *****",
    ])

    sig_eight_b = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "******",
        "*     *",
        "*     *",
        "******",
    ])

    sig_x = _bitmap_signature([
        "*     *",
        "**    *",
        "* *   *",
        "*  *  *",
        "*   * *",
        "*    **",
        "*     *",
    ])

    sig_x2 = _bitmap_signature([
        "*     *",
        " *   *",
        "  * *",
        "   *",
        "  * *",
        " *   *",
        "*     *",
    ])

    sig_x3 = _bitmap_signature([
        "  ***",
        " *   *",
        "*   * *",
        "*  *  *",
        "* *   *",
        " *   *",
        "  ***",
    ])

    sig_x3 = _bitmap_signature([
        "  ***",
        " *   *",
        "*   * *",
        "*  *  *",
        "* *   *",
        " *   *",
        "  ***",
    ])


    sig_e = _bitmap_signature([
        "*******",
        "*",
        "*",
        "****",
        "*",
        "*",
        "*******",
    ])

    sig_four = _bitmap_signature([
        "    *",
        "   **",
        "  * *",
        " *  *",
        "*******",
        "    *",
        "    *",
    ])

    sig_i = _bitmap_signature([
        "*******",
        "   *",
        "   *",
        "   *",
        "   *",
        "   *",
        "*******",
    ])

    sig_seven = _bitmap_signature([
        "*******",
        "     *",
        "    *",
        "   *",
        "  *",
        " *",
        "*******",
    ])

    sig_y = _bitmap_signature([
        "*     *",
        " *   *",
        "  * *",
        "   *",
        "   *",
        "   *",
        "   *",
    ])

    sig_w = _bitmap_signature([
        "*     *",
        "*     *",
        "*     *",
        "*  *  *",
        "* * * *",
        "**   **",
        "*     *",
    ])

    sig_m = _bitmap_signature([
        "*     *",
        "**   **",
        "* * * *",
        "*  *  *",
        "*     *",
        "*     *",
        "*     *",
    ])

    sig_p = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "******",
        "*",
        "*",
        "*",
    ])

    sig_g = _bitmap_signature([
        " *****",
        "*     *",
        "      *",
        "    **",
        "      *",
        "*     *",
        " *****",
    ])

    sig_g2 = _bitmap_signature([
        " *****",
        "*     *",
        "      *",
        "     **",
        "      *",
        "*     *",
        " *****",
    ])

    sig_g3 = _bitmap_signature([
        " *****",
        "*     *",
        "*",
        "*",
        "*   ***",
        "*     *",
        " *****",
    ])

    sig_y2 = _bitmap_signature([
        "*     *",
        "*     *",
        "  *   *",
        "  *   *",
        "   * *",
        "   * *",
        "    *",
    ])

    sig_h = _bitmap_signature([
        "*     *",
        "*     *",
        "*     *",
        "*******",
        "*     *",
        "*     *",
        "*     *",
    ])

    sig_l = _bitmap_signature([
        "*",
        "*",
        "*",
        "*",
        "*",
        "*",
        "*******",
    ])

    sig_one_topbar = _bitmap_signature([
        "*******",
        "   *",
        "   *",
        "   *",
        "   *",
        "   *",
        "   *",
    ])

    sig_r = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "******",
        "*   *",
        "*    *",
        "*     *",
    ])

    # Additional letters/digits observed in log

    sig_d = _bitmap_signature([
        "******",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "******",
    ])
    sig_c = _bitmap_signature([
        " *****",
        "*     *",
        "*",
        "*",
        "*",
        "*     *",
        " *****",
    ])

    sig_a = _bitmap_signature([
        "   *",
        "  * *",
        "  * *",
        " *   *",
        " *****",
        "*     *",
        "*     *",
    ])

    sig_u = _bitmap_signature([
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        "*     *",
        " *****",
    ])

    sig_j = _bitmap_signature([
        "      *",
        "      *",
        "      *",
        "      *",
        "      *",
        "*     *",
        " *****",
    ])

    sig_seven_no_bottom = _bitmap_signature([
        "*******",
        "     *",
        "    *",
        "   *",
        "  *",
        " *",
        "*",
    ])

    # Additional tolerant patterns for visually similar 'O'
    sig_O = sig_zero

    known_map = {
        sig_zero: "0",
        sig_O: "O",
        sig_eight: "8",
        sig_eight_b: "8",
        sig_x: "X",
        sig_x2: "X",
        sig_e: "E",
        sig_four: "4",
        sig_i: "I",
        sig_seven: "7",
        sig_y: "Y",
        sig_w: "W",
        sig_m: "M",
        sig_p: "P",
        sig_g: "G",
        sig_g2: "G",
        sig_g3: "G",
        sig_y2: "Y",
        sig_h: "H",
        sig_l: "L",
        sig_one_topbar: "1",
        sig_r: "R",
        sig_c: "C",
        sig_a: "A",
        sig_u: "U",
        sig_j: "J",
        sig_seven_no_bottom: "7",
    }

    decoded_chars: List[str] = []

    logger.info("=== CAPTCHA CHAR BITMAPS BEGIN ===")
    for idx, bmp in enumerate(char_bitmaps):
        logger.info(f"[CHAR {idx}]")
        for line in bmp:
            logger.info(line)
        logger.info("---")

        sig = _bitmap_signature(bmp)
        ch = known_map.get(sig)
        if ch is None:
            ch = "?"
            logger.info(f"[CHAR {idx}] UNKNOWN SIGNATURE:\n{sig}")

        decoded_chars.append(ch)

    logger.info("=== CAPTCHA CHAR BITMAPS END ===")

    captcha_text = "".join(decoded_chars)
    logger.info(f"[CAPTCHA DECODED] {captcha_text}")
    return captcha_text


def _massage_payload_for_submit(payload: Dict[str, str], captcha_text: str) -> Dict[str, str]:
    """
    Adjust the scraped form payload so it matches a real "continue / submit" click.
    Injects:
    - __EVENTTARGET = proxyActionBar:x:_cmdSave
    - __LASTFOCUS   = body_x_prxCaptcha_x_txtCaptcha
    - Captcha text
    - A few other workflow flags OhioBuys expects
    """

    payload["__LASTFOCUS"] = "body_x_prxCaptcha_x_txtCaptcha"
    payload["__EVENTTARGET"] = "proxyActionBar:x:_cmdSave"
    payload["__EVENTARGUMENT"] = ""

    # The page posts these
    payload.setdefault("REQUEST_METHOD", "GET")
    payload.setdefault("HTTP_RESOLUTION", "")

    # Inject our decoded captcha back into any captcha-like field
    for k in list(payload.keys()):
        if "prxCaptcha" in k and k.endswith("txtCaptcha"):
            payload[k] = captcha_text

    # These "header:" style names showed up in your PowerShell body
    payload["header:x:prxHeaderLogInfo:x:ContrastModal:chkContrastTheme_radio"] = "true"
    payload["header:x:prxHeaderLogInfo:x:ContrastModal:chkContrastTheme"] = "True"
    payload.setdefault("header:x:prxHeaderLogInfo:x:ContrastModal:chkPassiveNotification", "0")

    # Workflow-related extras we know they sometimes expect
    payload.setdefault("proxyActionBar:x:_cmdSave", "")
    payload.setdefault("proxyActionBar:x:txtWflRefuseMessage", "")
    payload.setdefault("hdnMandatory", "0")
    payload.setdefault("hdnWflAction", "")
    payload.setdefault("body:_ctl0", "")

    return payload


# ------------------------
# browse page parsing
# ------------------------

def _parse_rows_from_html(html: str) -> List[Dict[str, Any]]:
    """
    After we're past access_check, /rfp/request_browse_public returns HTML with inline JS vars
    like __ivHtmlControls['body_x_grid_grd_tr_<ROWID>_..._ctlXX'].
    We assemble those ctlXX pieces into a structured record per opportunity.
    """
    # Build buckets of ctlXX values per discovered row id
    buckets: Dict[str, Dict[str, str]] = {}
    for match in CELL_PATTERN.finditer(html):
        rowid = match.group("rowid")
        ctl = match.group("ctl")
        raw_html = match.group("html")
        buckets.setdefault(rowid, {})[ctl] = raw_html

    # Collect row ids either via tolerant ROW_ID_PATTERN or from the buckets we just built
    row_ids = set(ROW_ID_PATTERN.findall(html)) or set(buckets.keys())

    results: List[Dict[str, Any]] = []

    for rowid in row_ids:
        cells = buckets.get(rowid, {})

        c00 = cells.get("ctl00", "")  # solicitation / link
        c01 = cells.get("ctl01", "")  # title
        c02 = cells.get("ctl02", "")  # agency
        c03 = cells.get("ctl03", "")  # due date
        c04 = cells.get("ctl04", "")  # type
        c05 = cells.get("ctl05", "")  # status

        solicitation_text = _clean_html_to_text(c00)
        if (
            not solicitation_text
            or solicitation_text.startswith("*")
            or "Solicitation" in solicitation_text
        ):
            # skip header or junk non-row blocks
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
                "date_added": datetime.now(timezone.utc),  # 👈 NEW
                
            }
        )

    return results


# ------------------------
# main entrypoint
# ------------------------

async def fetch() -> List[Dict[str, Any]]:
    """
    1. Start a requests.Session() that pretends to be Chrome.
    2. GET /bas/access_check -> get form fields, captcha art.
    3. Solve captcha (using our bitmap mapping).
    4. POST /bas/access_check with __EVENTTARGET etc + captcha text.
    5. With that now-authorized session, GET /rfp/request_browse_public.
    6. Parse bids out of the inline JS and return them as row dicts.
    """
    logger.info("Starting OhioBuys scrape (requests session + captcha decode)...")

    # Create a Cloudflare-aware HTTP session and optionally inject cookies
    session = _create_http_session()
    cookie_str = os.getenv("OHIOBUYS_COOKIES", "").strip()
    if cookie_str:
        _apply_cookie_string(session, cookie_str)
        logger.info("Applied cookies from OHIOBUYS_COOKIES env var.")

    outer_max = int(os.getenv("OHIOBUYS_MAX_ACCESS_ATTEMPTS", "3") or "3")
    for outer in range(1, outer_max + 1):
        # Step 1: GET access_check to collect cookies + hidden inputs + captcha table
        r_get = session.get(ACCESS_CHECK_URL)
        if r_get.status_code != 200:
            logger.info(f"access_check GET failed: {r_get.status_code}")
            return []

        # Detect Cloudflare interstitials and attempt a cloudscraper retry if needed
        if _is_cloudflare_block(r_get.status_code, r_get.text, dict(r_get.headers)):
            logger.info("Detected Cloudflare challenge on access_check. Retrying with cloudscraper...")
            if HAVE_CLOUDSCRAPER:
                session = _create_http_session(force_cloudscraper=True)
                if cookie_str:
                    _apply_cookie_string(session, cookie_str)
                r_get = session.get(ACCESS_CHECK_URL)
            if _is_cloudflare_block(r_get.status_code, r_get.text, dict(r_get.headers)):
                logger.info("Still blocked by Cloudflare after cloudscraper retry. Attempting Playwright fallback...")
                if HAVE_PLAYWRIGHT or os.getenv("OHIOBUYS_USE_PLAYWRIGHT", "").strip().lower() in ("1", "true", "yes", "on"):
                    html = await _playwright_get_browse_html(session)
                    if html:
                        rows = _parse_rows_from_html(html)
                        logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
                        return rows
                return []

        access_html = r_get.text
        soup = BeautifulSoup(access_html, "html.parser")
        logger.info(f"[ACCESS_CHECK DEBUG first1k] {access_html[:1000]}")

        # Step 2/3: repeatedly try to decode captcha; refresh if unknown chars appear
        max_attempts = int(os.getenv("OHIOBUYS_MAX_CAPTCHA_ATTEMPTS", "5") or "5")
        attempt = 0
        captcha_guess = ""
        solved = False
        while attempt < max_attempts:
            attempt += 1
            # capture all inputs into base payload for this attempt
            raw_payload = _collect_form_fields(soup)

            captcha_html_escaped = _extract_captcha_table_html(access_html)
            if captcha_html_escaped:
                decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
                char_bitmaps = decoded_info["char_bitmaps"]
                captcha_guess = _guess_captcha_text_from_bitmaps(char_bitmaps)
            else:
                logger.info("WARNING: could not locate captcha table script; guessing blank captcha.")
                captcha_guess = ""

            if captcha_guess and "?" not in captcha_guess:
                logger.info(f"Captcha decoded successfully on attempt {attempt}: {captcha_guess}")
                solved = True
                break
            else:
                logger.info(f"Captcha decode contained unknown glyphs on attempt {attempt}. Refreshing...")
                r_get = session.get(ACCESS_CHECK_URL)
                access_html = r_get.text if r_get.status_code == 200 else ""
                soup = BeautifulSoup(access_html, "html.parser")
                if not access_html:
                    logger.info("Failed to refresh access_check while retrying captcha.")
                    break

        if not solved:
            logger.info("Captcha decoding failed after retries; not submitting invalid captcha.")
            continue

    # Step 4: massage payload (inject captcha_guess, eventtarget, etc.)
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

        # Step 5: POST back to access_check to "enter" the public portal
        r_post = session.post(
            ACCESS_CHECK_URL,
            data=payload,
            headers=post_headers,
            allow_redirects=True,
        )

        logger.info(f"[POST access_check status] {r_post.status_code} final_url={r_post.url}")

        # Step 6: Now request the real browse page with this same unlocked session
        r_browse = session.get(BROWSE_URL, allow_redirects=True)
        logger.info(f"[GET browse_public status] {r_browse.status_code} url={r_browse.url}")

        # Debug snippet so we can confirm whether we got the grid or got bounced back to access_check again
        logger.info(f"[BROWSE DEBUG first2k] {r_browse.text[:2000]}")

        # If browse still points at access_check, retry a fresh captcha cycle
        if "/bas/access_check" in r_browse.url:
            logger.info(f"Browse landed on access_check after POST; retrying full cycle ({outer}/{outer_max})...")
            continue

        if r_browse.status_code != 200:
            # Last-chance fallback using Playwright if available
            if _is_cloudflare_block(r_browse.status_code, r_browse.text, dict(r_browse.headers)) and (HAVE_PLAYWRIGHT or os.getenv("OHIOBUYS_USE_PLAYWRIGHT", "").strip().lower() in ("1", "true", "yes", "on")):
                html = await _playwright_get_browse_html(session)
                if html:
                    rows = _parse_rows_from_html(html)
                    logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
                    return rows
            return []

        # Step 7: Parse final HTML/JS for bid rows
        rows = _parse_rows_from_html(r_browse.text)
        if not rows:
            if HAVE_PLAYWRIGHT or os.getenv("OHIOBUYS_USE_PLAYWRIGHT", "").strip().lower() in ("1", "true", "yes", "on"):
                logger.info("No rows parsed from static HTML; attempting Playwright-rendered content...")
                html = await _playwright_get_browse_html(session)
                if html:
                    rows = _parse_rows_from_html(html)
            else:
                logger.info("No rows parsed from static HTML and Playwright fallback not enabled. Set OHIOBUYS_USE_PLAYWRIGHT=1 to try rendered content.")
        logger.info(f"OhioBuys: scraped {len(rows)} opportunities.")

        return rows

    # Exhausted outer attempts; final fallback via Playwright if allowed
    if HAVE_PLAYWRIGHT or os.getenv("OHIOBUYS_USE_PLAYWRIGHT", "").strip().lower() in ("1", "true", "yes", "on"):
        html = await _playwright_get_browse_html(session)
        if html:
            rows = _parse_rows_from_html(html)
            logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
            return rows

    return []
