import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
import datetime
from datetime import datetime, timezone


import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger("columbus")

BASE = "https://ohiobuys.ohio.gov"
ACCESS_CHECK_URL = BASE + "/page.aspx/en/bas/access_check"
BROWSE_URL = BASE + "/page.aspx/en/rfp/request_browse_public"

# --- regexes for final browse page parsing ---

# Each row has an internal numeric row id. We key off 'body_x_grid_grd_tr_<ROWID>_'.
ROW_ID_PATTERN = re.compile(
    r"__ivHtmlControls\['body_x_grid_grd_tr_(\d+)_", re.IGNORECASE
)

# Each cell for that row shows up in a JS assignment like:
# __ivHtmlControls['body_x_grid_grd_tr_48362_xxx_ctl00'] = "<a ...>SRC00000123</a>";
# ctl00 = solicitation/link, ctl01 = title, ctl02 = agency, ctl03 = due, ctl04 = type, ctl05 = status
CELL_PATTERN = re.compile(
    r"__ivHtmlControls\['body_x_grid_grd_tr_(?P<rowid>\d+)[^']*?_(?P<ctl>ctl\d+)'\]\s*=\s*\"(?P<html>.*?)\";",
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
    - strip trailing whitespace on each row
    - join rows with '\n'
    - trim leading/trailing newlines
    """
    return "\n".join(line.rstrip() for line in bmp).strip("\n")


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

    sig_zero = _bitmap_signature([
        " *****",
        "*     *",
        "*",
        "*",
        "*",
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

    sig_x = _bitmap_signature([
        "*     *",
        "**    *",
        "* *   *",
        "*  *  *",
        "*   * *",
        "*    **",
        "*     *",
    ])

    known_map = {
        sig_zero: "0",
        sig_eight: "8",
        sig_x: "X",
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

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Step 1: GET access_check to collect cookies + hidden inputs + captcha table
    r_get = session.get(ACCESS_CHECK_URL)
    if r_get.status_code != 200:
        logger.info(f"access_check GET failed: {r_get.status_code}")
        return []

    access_html = r_get.text
    soup = BeautifulSoup(access_html, "html.parser")

    # debug: confirm we really hit access_check
    logger.info(f"[ACCESS_CHECK DEBUG first1k] {access_html[:1000]}")

    # Step 2: capture all inputs into base payload
    raw_payload = _collect_form_fields(soup)

    # Step 3: pull captcha ascii art, split into character bitmaps, decode to text
    captcha_html_escaped = _extract_captcha_table_html(access_html)
    captcha_guess = ""
    if captcha_html_escaped:
        decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
        char_bitmaps = decoded_info["char_bitmaps"]
        captcha_guess = _guess_captcha_text_from_bitmaps(char_bitmaps)
    else:
        logger.info("WARNING: could not locate captcha table script; guessing blank captcha.")
        captcha_guess = ""

    # Step 4: massage payload (inject captcha_guess, eventtarget, etc.)
    payload = _massage_payload_for_submit(raw_payload, captcha_guess)

    post_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE,
        "Referer": ACCESS_CHECK_URL,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
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

    if r_browse.status_code != 200:
        return []

    # Step 7: Parse final HTML/JS for bid rows
    rows = _parse_rows_from_html(r_browse.text)
    logger.info(f"OhioBuys: scraped {len(rows)} opportunities.")

    return rows
