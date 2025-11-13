import asyncio

import logging

import re

import secrets

import os

import json

import random

import time

from typing import List, Dict, Any, Optional, Tuple

from datetime import datetime, timezone

from pathlib import Path

from functools import lru_cache

 

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

CAPTCHA_DISTANCE_MULTIPLIER = float(
    os.getenv("OHIOBUYS_CAPTCHA_DISTANCE_MULTIPLIER", "0.34")
)
CAPTCHA_DISTANCE_MIN = int(os.getenv("OHIOBUYS_CAPTCHA_DISTANCE_MIN", "12"))
CAPTCHA_TOTAL_DISTANCE_PER_CHAR = float(
    os.getenv("OHIOBUYS_CAPTCHA_TOTAL_DISTANCE_PER_CHAR", "20")
)
CAPTCHA_TOTAL_DISTANCE_MIN = int(
    os.getenv("OHIOBUYS_CAPTCHA_TOTAL_DISTANCE_MIN", "65")
)
STATUS_FILTER_LABEL = os.getenv("OHIOBUYS_STATUS_FILTER", "Open for Bidding").strip()
USE_PLAYWRIGHT_PAGINATION = (
    os.getenv("OHIOBUYS_USE_PLAYWRIGHT_PAGINATION", "1").strip().lower()
    not in {"0", "false", "no"}
)


def _human_delay(min_s: float = 0.4, max_s: float = 1.2) -> None:
    """Sleep for a random interval to mimic human browsing."""

    try:
        time.sleep(random.uniform(min_s, max_s))
    except Exception:
        pass


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

        "%m/%d/%Y %I:%M:%S %p",

        "%m/%d/%Y %I:%M %p",

        "%m/%d/%Y %H:%M",

        "%m/%d/%Y %H:%M:%S",

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

 

def _normalize_bitmap_rows(bmp: List[str]) -> List[str]:

    """

    Trim empty rows/columns so signatures remain stable even if spacing shifts.

    """

 

    if not bmp:

        return []

 

    lines = [line.rstrip("\r\n") for line in bmp]

 

    if not any(line.strip() for line in lines):

        # All blank - keep a single blank row so downstream logic still works.

        return [" "]

 

    first_row = 0

    last_row = len(lines) - 1

 

    for idx, line in enumerate(lines):

        if line.strip():

            first_row = idx

            break

 

    for idx in range(len(lines) - 1, -1, -1):

        if lines[idx].strip():

            last_row = idx

            break

 

    trimmed_rows = lines[first_row : last_row + 1]

    max_width = max(len(row) for row in trimmed_rows)

    padded_rows = [row.ljust(max_width) for row in trimmed_rows]

 

    first_col = None

    last_col = None

 

    for col in range(max_width):

        if any(row[col] == "*" for row in padded_rows):

            first_col = col

            break

 

    for col in range(max_width - 1, -1, -1):

        if any(row[col] == "*" for row in padded_rows):

            last_col = col

            break

 

    if first_col is None or last_col is None:

        # Fallback - no solid pixels discovered.

        return [" " * max_width for _ in padded_rows]

 

    normalized = [row[first_col : last_col + 1] for row in padded_rows]

    return normalized

 
def _bitmap_signature(bmp: List[str]) -> str:

    """

    Normalize a bitmap into a canonical multi-line signature:

    - trim empty rows/columns

    - join rows with '\n'

    - trim leading/trailing newlines

    """

    normalized_rows = _normalize_bitmap_rows(bmp)
    return "\n".join(normalized_rows).strip("\n")


def _bitmap_to_matrix(bmp: List[str]) -> List[List[int]]:

    """

    Convert a bitmap into a 2-D matrix of 1s/0s for precise comparison.

    """

    normalized_rows = _normalize_bitmap_rows(bmp)
    if not normalized_rows:
        return []

    return [[1 if ch == "*" else 0 for ch in row] for row in normalized_rows]


def _bitmap_features(matrix: List[List[int]]) -> Dict[str, Any]:

    """

    Pre-compute simple bitmap features that help stabilize fuzzy matching.

    """

    if not matrix:
        return {
            "pixel_count": 0,
            "row_proj": [],
            "col_proj": [],
            "height": 0,
            "width": 0,
        }

    height = len(matrix)
    width = len(matrix[0]) if height else 0
    row_proj = [sum(row) for row in matrix]
    col_proj = [sum(matrix[r][c] for r in range(height)) for c in range(width)]
    pixel_count = sum(row_proj)

    return {
        "pixel_count": pixel_count,
        "row_proj": row_proj,
        "col_proj": col_proj,
        "height": height,
        "width": width,
    }


def _pixel_at(matrix: List[List[int]], row: int, col: int) -> int:

    if row < 0 or col < 0:
        return 0
    if row >= len(matrix):
        return 0
    current_row = matrix[row]
    if col >= len(current_row):
        return 0
    return current_row[col]


def _matrix_pixel_distance(
    matrix_a: List[List[int]], matrix_b: List[List[int]]
) -> int:

    height = max(len(matrix_a), len(matrix_b))
    width = max(
        len(matrix_a[0]) if matrix_a else 0, len(matrix_b[0]) if matrix_b else 0
    )

    distance = 0
    for r in range(height):
        for c in range(width):
            distance += abs(_pixel_at(matrix_a, r, c) - _pixel_at(matrix_b, r, c))
    return distance


def _projection_distance(proj_a: List[int], proj_b: List[int]) -> int:

    max_len = max(len(proj_a), len(proj_b))
    total = 0
    for idx in range(max_len):
        val_a = proj_a[idx] if idx < len(proj_a) else 0
        val_b = proj_b[idx] if idx < len(proj_b) else 0
        total += abs(val_a - val_b)
    return total


def _per_char_distance_threshold(matrix: List[List[int]]) -> float:

    height = len(matrix)
    width = len(matrix[0]) if height else 0
    area = max(width * height, 1)
    base = CAPTCHA_DISTANCE_MULTIPLIER * area
    return max(base, float(CAPTCHA_DISTANCE_MIN))


def _max_total_distance(expected_chars: int) -> float:

    per_char = CAPTCHA_TOTAL_DISTANCE_PER_CHAR * max(expected_chars, 1)
    return max(per_char, float(CAPTCHA_TOTAL_DISTANCE_MIN))

 
@lru_cache(maxsize=1)
def _get_known_character_signatures() -> List[Dict[str, Any]]:

    """

    Returns all known character bitmap signatures along with derived metadata.

    """

    sigs: Dict[str, str] = {}

 

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

 

    sigs["0_alt"] = _bitmap_signature([

        " ******",

        "*      *",

        "*      *",

        "*      *",

        "*      *",

        "*      *",

        " ******",

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

 

    sigs["2"] = _bitmap_signature([

        " *****",

        "*     *",

        "      *",

        "    **",

        "  **",

        " **",

        "*******",

    ])

 

    sigs["2_alt"] = _bitmap_signature([

        " *****",

        "*     *",

        "      *",

        "   ***",

        " **",

        "*",

        "*******",

    ])

 

    sigs["3"] = _bitmap_signature([

        " *****",

        "*     *",

        "      *",

        "   ***",

        "      *",

        "*     *",

        " *****",

    ])

 

    sigs["3_alt"] = _bitmap_signature([

        "******",

        "     *",

        "     *",

        "  ****",

        "     *",

        "     *",

        "******",

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

 

    sigs["5"] = _bitmap_signature([

        "*******",

        "*",

        "*",

        "******",

        "      *",

        "      *",

        "******",

    ])

 

    sigs["5_alt"] = _bitmap_signature([

        "******",

        "*",

        "*",

        "*****",

        "     *",

        "     *",

        "*****",

    ])

 

    sigs["6"] = _bitmap_signature([

        " *****",

        "*",

        "*",

        "******",

        "*     *",

        "*     *",

        " *****",

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

 

    sigs["9"] = _bitmap_signature([

        " *****",

        "*     *",

        "*     *",

        " ******",

        "      *",

        "      *",

        " *****",

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

 

    sigs["A_alt"] = _bitmap_signature([

        "  ***",

        " *   *",

        "*     *",

        "*     *",

        "*******",

        "*     *",

        "*     *",

    ])

 

    sigs["B"] = _bitmap_signature([

        "******",

        "*     *",

        "*     *",

        "******",

        "*     *",

        "*     *",

        "******",

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

 

    sigs["C_alt"] = _bitmap_signature([

        " *****",

        "*     *",

        "*",

        "*",

        "*",

        "*",

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

 

    sigs["F"] = _bitmap_signature([

        "*******",

        "*",

        "*",

        "*****",

        "*",

        "*",

        "*",

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

 

    sigs["K"] = _bitmap_signature([

        "*    *",

        "*   *",

        "*  *",

        "***",

        "*  *",

        "*   *",

        "*    *",

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

 

    sigs["N"] = _bitmap_signature([

        "*     *",

        "**    *",

        "* *   *",

        "*  *  *",

        "*   * *",

        "*    **",

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

 

    sigs["O_alt"] = _bitmap_signature([

        "*******",

        "*     *",

        "*     *",

        "*     *",

        "*     *",

        "*     *",

        "*******",

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

 

    sigs["Q"] = _bitmap_signature([

        " *****",

        "*     *",

        "*     *",

        "*     *",

        "*   * *",

        "*    **",

        " **** *",

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

 

    sigs["S"] = _bitmap_signature([

        " *****",

        "*     *",

        "*",

        " *****",

        "      *",

        "*     *",

        " *****",

    ])

 

    sigs["T"] = _bitmap_signature([

        "*******",

        "   *",

        "   *",

        "   *",

        "   *",

        "   *",

        "   *",

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

 

    sigs["V"] = _bitmap_signature([

        "*     *",

        "*     *",

        " *   *",

        " *   *",

        "  * *",

        "   *",

        "   *",

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

 

    sigs["Z"] = _bitmap_signature([

        "*******",

        "     *",

        "    *",

        "   *",

        "  *",

        " *",

        "*******",

    ])

 

    entries: List[Dict[str, Any]] = []

    for char, sig in sigs.items():

        # Remove variant suffixes (_alt, _alt1, etc.)

        base_char = char.split("_")[0]

        rows = sig.split("\n") if sig else []

        matrix = _bitmap_to_matrix(rows)

        entries.append(

            {

                "char": base_char,

                "signature": sig,

                "matrix": matrix,

                "features": _bitmap_features(matrix),

            }

        )

 

    return entries

 

 

def _fuzzy_match_character(bmp: List[str]) -> Tuple[str, float, Dict[str, Any]]:

    """

    Match a character bitmap using 2-D comparisons plus feature projections.

    Returns ("?", score, details) if no good match is found.

    """

    matrix = _bitmap_to_matrix(bmp)
    features = _bitmap_features(matrix)
    threshold = _per_char_distance_threshold(matrix)
    known_sigs = _get_known_character_signatures()

    best_char = "?"
    best_score = float("inf")
    best_components: Dict[str, Any] = {
        "pixel_distance": float("inf"),
        "pixel_count_penalty": float("inf"),
        "row_penalty": float("inf"),
        "col_penalty": float("inf"),
        "threshold": threshold,
    }

    for entry in known_sigs:
        target_features = entry["features"]
        pixel_distance = _matrix_pixel_distance(matrix, entry["matrix"])
        pixel_count_penalty = abs(
            features["pixel_count"] - target_features["pixel_count"]
        )
        row_penalty = _projection_distance(
            features["row_proj"], target_features["row_proj"]
        )
        col_penalty = _projection_distance(
            features["col_proj"], target_features["col_proj"]
        )

        score = (
            pixel_distance
            + 0.5 * pixel_count_penalty
            + 0.75 * row_penalty
            + 0.75 * col_penalty
        )

        if score < best_score:
            best_score = score
            best_char = entry["char"]
            best_components = {
                "pixel_distance": pixel_distance,
                "pixel_count_penalty": pixel_count_penalty,
                "row_penalty": row_penalty,
                "col_penalty": col_penalty,
                "threshold": threshold,
            }

    if best_score > threshold:
        return "?", best_score, best_components

    best_components["threshold"] = threshold
    return best_char, best_score, best_components

 

 

def _save_unknown_bitmap(bmp: List[str], captcha_attempt: int) -> None:

    """

    Save unknown character bitmaps to a learning file for future analysis.

    """

    try:

        learn_dir = Path("logs/captcha_learning")

        learn_dir.mkdir(parents=True, exist_ok=True)

 

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = learn_dir / f"unknown_{timestamp}_{captcha_attempt}.txt"

 

        normalized = _normalize_bitmap_rows(bmp)

        with open(filename, "w") as f:

            f.write("# Add this to _get_known_character_signatures():\n")

            f.write('sigs["?"] = _bitmap_signature([\n')

            for line in normalized:

                f.write(f'    "{line}",\n')

            f.write("])\n\n")

            f.write("# Raw bitmap:\n")

            for line in bmp:

                f.write(f"{line}\n")

 

        logger.info(f"Saved unknown bitmap to {filename}")

    except Exception as e:

        logger.warning(f"Failed to save unknown bitmap: {e}")

 

 

def _guess_captcha_text_from_bitmaps(
    char_bitmaps: List[List[str]], attempt: int = 0
) -> Dict[str, Any]:

    """

    Convert each per-character bitmap block into the actual character using fuzzy matching.

    """

    decoded_chars: List[str] = []
    per_char_scores: List[float] = []
    per_char_details: List[Dict[str, Any]] = []
    unknown_found = False
    unknown_indices: List[int] = []

    logger.info("=== CAPTCHA CHAR BITMAPS BEGIN ===")

    for idx, bmp in enumerate(char_bitmaps):
        logger.info(f"[CHAR {idx}]")
        for line in bmp:
            logger.info(line)
        logger.info("---")

        char, score, detail = _fuzzy_match_character(bmp)
        per_char_scores.append(score)
        per_char_details.append(detail)

        if char == "?":
            unknown_found = True
            unknown_indices.append(idx)
            logger.warning(
                f"[CHAR {idx}] UNKNOWN (score={score:.2f} / threshold={detail['threshold']:.2f})"
            )
            _save_unknown_bitmap(bmp, attempt)
        else:
            logger.info(
                f"[CHAR {idx}] Matched '{char}' (score={score:.2f} / threshold={detail['threshold']:.2f})"
            )

        decoded_chars.append(char)

    logger.info("=== CAPTCHA CHAR BITMAPS END ===")

    captcha_text = "".join(decoded_chars)
    total_distance = sum(per_char_scores)
    max_total = _max_total_distance(len(decoded_chars))

    logger.info(
        f"[CAPTCHA DECODED] {captcha_text} (unknown={unknown_found}, total_score={total_distance:.2f}/{max_total:.2f})"
    )

    return {
        "text": captcha_text,
        "has_unknown": unknown_found,
        "per_char_scores": per_char_scores,
        "per_char_details": per_char_details,
        "unknown_indices": unknown_indices,
        "total_distance": total_distance,
        "max_total_distance": max_total,
    }


def _empty_guess_info() -> Dict[str, Any]:

    return {
        "text": "",
        "has_unknown": True,
        "per_char_scores": [],
        "per_char_details": [],
        "unknown_indices": [],
        "total_distance": float("inf"),
        "max_total_distance": 0.0,
    }


def _is_confident_captcha_guess(guess: Dict[str, Any]) -> bool:

    if not guess.get("text"):
        return False
    if guess.get("has_unknown"):
        return False
    score = guess.get("total_distance", float("inf"))
    limit = guess.get("max_total_distance", float("inf"))
    return isinstance(score, (int, float)) and isinstance(
        limit, (int, float)
    ) and score <= limit


def _guess_rejection_reason(guess: Dict[str, Any]) -> str:

    if not guess.get("text"):
        return "empty result"
    if guess.get("has_unknown"):
        return "unknown characters"
    score = guess.get("total_distance", float("inf"))
    limit = guess.get("max_total_distance", float("inf"))
    if (
        isinstance(score, (int, float))
        and isinstance(limit, (int, float))
        and score > limit
    ):
        return f"score {score:.2f} exceeds limit {limit:.2f}"
    return "insufficient confidence"

 

 

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

                        guess_info = _empty_guess_info()

                        if captcha_html_escaped:

                            decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)

                            char_bitmaps = decoded_info["char_bitmaps"]

                            guess_info = _guess_captcha_text_from_bitmaps(char_bitmaps, attempt)

 

                        if _is_confident_captcha_guess(guess_info):

                            captcha_guess = guess_info["text"]

                            logger.info(

                                "[Playwright] Captcha accepted '%s' (score=%.2f/%.2f)",

                                captcha_guess,

                                guess_info["total_distance"],

                                guess_info["max_total_distance"],

                            )

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

                            reason = _guess_rejection_reason(guess_info)

                            logger.info(

                                f"[Playwright] Captcha rejected ({reason}); refreshing."

                            )

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


def _parse_rows_from_html(html: str) -> List[Dict[str, Any]]:

    """

    Parse opportunities from the browse page HTML.

    Prefers the modern table markup; falls back to legacy inline controls.

    """

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="body_x_grid_grd")
    if table:
        rows = _parse_rows_from_table(table)
        if rows:
            return rows

    return _parse_rows_from_inline_controls(html)


def _normalize_status_label(status_text: str) -> str:
    text = (status_text or "").strip()
    lower = text.lower()
    if "open for bidding" in lower:
        return "Open"
    return text or "Open"


def _parse_rows_from_table(table_soup: Any) -> List[Dict[str, Any]]:

    """

    Parse the rendered grid rows from the browse table markup.

    """

    results: List[Dict[str, Any]] = []

    def _cell_text(cells: List[Any], idx: int) -> str:
        if idx < len(cells):
            return cells[idx].get_text(" ", strip=True)
        return ""

    for tr in table_soup.select("tbody tr[data-id]"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue

        solicitation_id = _cell_text(cells, 1)
        if not solicitation_id:
            continue

        title_text = _cell_text(cells, 2)
        end_date_et = _cell_text(cells, 5)
        end_date_utc = _cell_text(cells, 11)
        inquiry_end = _cell_text(cells, 6)
        agency_text = _cell_text(cells, 9)
        status_text = _normalize_status_label(_cell_text(cells, 12))
        solicitation_type = _cell_text(cells, 14)
        commodity_text = _cell_text(cells, 7)
        begin_date_et = _cell_text(cells, 4)
        begin_date_utc = _cell_text(cells, 10)

        due_dt = _parse_due_date(end_date_et) or _parse_due_date(end_date_utc)
        posted_dt = _parse_due_date(begin_date_et) or _parse_due_date(begin_date_utc)
        prebid_dt = _parse_due_date(inquiry_end)

        link = tr.select_one("a[href]")
        if link:
            href = link["href"]
            if not href.startswith("http"):
                source_url = urljoin(BASE + "/", href.lstrip("/"))
            else:
                source_url = href
        else:
            source_url = BROWSE_URL

        results.append(
            {
                "external_id": solicitation_id,
                "title": title_text,
                "agency_name": agency_text,
                "due_date": due_dt,
                "posted_date": posted_dt,
                "status": status_text or "Open",
                "category": solicitation_type or "RFP/RFQ",
                "source_url": source_url,
                "attachments": [],
                "summary": commodity_text,
                "full_text": "",
                "source": "OhioBuys",
                "keyword_tag": None,
                "location_geo": "",
                "prebid_date": prebid_dt,
                "date_added": datetime.now(timezone.utc),
            }
        )

    return results


def _parse_rows_from_inline_controls(html: str) -> List[Dict[str, Any]]:

    """

    Legacy fallback parser for the inline __ivHtmlControls definitions.

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
        status_text = _normalize_status_label(_clean_html_to_text(c05))

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


def _html_has_additional_pages(html: str) -> bool:

    soup = BeautifulSoup(html, "html.parser")
    next_btn = soup.select_one("#body_x_grid_PagerBtnNextPage")
    if next_btn:
        classes = " ".join(next_btn.get("class", [])).lower()
        if "disabled" not in classes:
            return True
    page_buttons = soup.select("button[id^='body_x_grid_PagerBtn'][data-page-index]")
    for btn in page_buttons:
        data_idx = btn.get("data-page-index")
        classes = " ".join(btn.get("class", [])).lower()
        if data_idx not in {None, "0", "-1"} and "hidden" not in classes:
            return True
    return False


def _filter_rows_by_status(
    rows: List[Dict[str, Any]], status_label: str
) -> List[Dict[str, Any]]:

    if not status_label:
        return rows
    desired = _normalize_status_label(status_label).lower()
    filtered: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        status = (row.get("status") or "").lower()
        if desired in status:
            ext_id = row.get("external_id")
            if ext_id and ext_id not in seen_ids:
                seen_ids.add(ext_id)
                filtered.append(row)
    if not filtered:
        logger.info(
            "No rows matched status '%s' on this page; dropping %s rows.",
            status_label,
            len(rows),
        )
    return filtered


def _apply_status_filter_to_html(
    session: requests.Session, soup: BeautifulSoup, status_label: str
) -> str:

    if not status_label:
        return soup.decode()

    payload = _collect_form_fields(soup)
    if not payload:
        return soup.decode()

    payload["body:x:selStatusCode_4"] = status_label
    payload["body_x_selStatusCode_4_search"] = status_label
    payload["__EVENTTARGET"] = ""
    payload["__EVENTARGUMENT"] = ""
    payload["body:x:prxFilterBar:x:cmdSearchBtn"] = "Search"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE,
        "Referer": BROWSE_URL,
    }
    try:
        _human_delay()
        resp = session.post(
            BROWSE_URL, data=payload, headers=headers, allow_redirects=True
        )
        if resp.status_code == 200 and "body_x_grid_grd" in resp.text:
            logger.info("Applied solicitation status filter via form submission.")
            return resp.text
    except Exception as exc:
        logger.warning(f"Failed to apply status filter via POST: {exc}")

    return soup.decode()


def _client_id_to_unique_id(client_id: str) -> str:
    return client_id.replace("_", ":")


def _post_grid_page(
    session: requests.Session,
    soup: BeautifulSoup,
    button_id: str,
    page_index: int,
) -> Optional[str]:

    payload = _collect_form_fields(soup)
    if not payload:
        return None

    payload["__EVENTTARGET"] = _client_id_to_unique_id(button_id)
    payload["__EVENTARGUMENT"] = ""
    payload["hdnCurrentPageIndexbody_x_grid_grd"] = str(page_index)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": BASE,
        "Referer": BROWSE_URL,
    }

    try:
        _human_delay()
        resp = session.post(
            BROWSE_URL, data=payload, headers=headers, allow_redirects=True
        )
        if resp.status_code == 200 and "body_x_grid_grd" in resp.text:
            return resp.text
        logger.warning(
            "Pagination POST for page %s failed: status=%s",
            page_index,
            resp.status_code,
        )
    except Exception as exc:
        logger.warning(f"Pagination POST failed: {exc}")
    return None


def _collect_additional_pages(
    session: requests.Session, first_html: str, status_label: str
) -> List[List[Dict[str, Any]]]:

    pages: List[List[Dict[str, Any]]] = []
    current_html = first_html
    visited: set[int] = {0}

    while True:
        soup = BeautifulSoup(current_html, "html.parser")
        page_candidates: List[Tuple[int, str]] = []
        for btn in soup.select("button[id^='body_x_grid_PagerBtn'][data-page-index]"):
            data_idx = btn.get("data-page-index")
            if data_idx is None:
                continue
            try:
                idx = int(data_idx)
            except ValueError:
                continue
            if idx in visited or idx < 0:
                continue
            btn_id = btn.get("id", "")
            if not btn_id or btn_id.endswith("NextPage") or btn_id.endswith("PrevPage"):
                continue
            page_candidates.append((idx, btn_id))

        if not page_candidates:
            break

        page_candidates.sort()
        next_idx, btn_id = page_candidates[0]
        logger.info(f"Requesting additional grid page index {next_idx} via form POST...")
        next_html = _post_grid_page(session, soup, btn_id, next_idx)
        if not next_html:
            break

        page_rows = _parse_rows_from_html(next_html)
        filtered_rows = _filter_rows_by_status(page_rows, status_label)
        if not filtered_rows:
            logger.info(
                "Pagination page %s returned no matching rows; stopping pagination.",
                next_idx,
            )
            break

        pages.append(filtered_rows)
        current_html = next_html
        visited.add(next_idx)

        if not _html_has_additional_pages(next_html):
            break

    return pages


async def _playwright_scrape_filtered_rows(status_label: str) -> List[Dict[str, Any]]:

    if not HAVE_PLAYWRIGHT:
        logger.warning("Playwright pagination requested but playwright packages unavailable.")
        return []

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception:
        logger.warning("Failed to import async Playwright; skipping pagination.")
        return []

    rows: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    max_attempts = int(os.getenv("OHIOBUYS_MAX_CAPTCHA_ATTEMPTS", "10") or "10")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=_default_headers().get("User-Agent"),
                extra_http_headers={
                    k: v for k, v in _default_headers().items() if k.lower() != "user-agent"
                },
            )
            page = await context.new_page()
            await page.goto(ACCESS_CHECK_URL, wait_until="domcontentloaded")

            solved = False
            for attempt in range(1, max_attempts + 1):
                access_html = await page.content()
                captcha_html_escaped = _extract_captcha_table_html(access_html)
                if not captcha_html_escaped:
                    await page.reload(wait_until="domcontentloaded")
                    continue

                decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
                char_bitmaps = decoded_info["char_bitmaps"]
                guess_info = _guess_captcha_text_from_bitmaps(char_bitmaps, attempt)

                if not _is_confident_captcha_guess(guess_info):
                    logger.info(
                        "[Playwright pagination] captcha attempt %s rejected (%s)",
                        attempt,
                        _guess_rejection_reason(guess_info),
                    )
                    await page.reload(wait_until="domcontentloaded")
                    continue

                captcha_text = guess_info["text"]
                try:
                    await page.fill("#body_x_prxCaptcha_x_txtCaptcha", captcha_text)
                    await page.click("#proxyActionBar_x__cmdSave")
                    await page.wait_for_timeout(1500)
                except Exception as exc:
                    logger.warning(f"Playwright captcha submission failed: {exc}")
                    await page.reload(wait_until="domcontentloaded")
                    continue

                if "access_check" not in page.url.lower():
                    solved = True
                    break

                await page.reload(wait_until="domcontentloaded")

            if not solved:
                logger.error("Playwright pagination: failed to solve captcha.")
                await context.close()
                await browser.close()
                return []

            await page.goto(BROWSE_URL, wait_until="domcontentloaded")

            for page_index in range(20):
                await page.wait_for_selector("#body_x_grid_grd")
                html = await page.content()
                page_rows = _parse_rows_from_html(html)
                for row in page_rows:
                    ext_id = row.get("external_id")
                    if ext_id and ext_id not in seen_ids:
                        seen_ids.add(ext_id)
                        rows.append(row)

                next_btn = page.locator("#body_x_grid_PagerBtnNextPage")
                try:
                    classes = (await next_btn.get_attribute("class")) or ""
                except Exception:
                    break

                if "disabled" in classes.lower():
                    break

                try:
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                except Exception as exc:
                    logger.warning(
                        f"Playwright pagination: failed to click next page: {exc}"
                    )
                    break

            await context.close()
            await browser.close()

    except NotImplementedError as exc:
        logger.warning(
            "Playwright pagination is not supported in this environment: %s", exc
        )
        return []
    except Exception as exc:
        logger.warning(f"Playwright pagination encountered an error: {exc}")
        return []

    return _filter_rows_by_status(rows, status_label)


# ------------------------

# main entrypoint

# ------------------------


async def fetch(force_playwright: bool = False) -> List[Dict[str, Any]]:

    """

    Main scraping function with improved captcha handling.

    Set force_playwright to skip HTTP mode and rely on the browser fallback.

    """

    logger.info("Starting OhioBuys scrape (improved captcha solver)...")
    logger.info(
        "Ensure OhioBuys scraping complies with posted terms; request official access when available."
    )

    env_force = os.getenv("OHIOBUYS_FORCE_PLAYWRIGHT", "").strip().lower()
    use_force_playwright = force_playwright or env_force in ("1", "true", "yes", "force")

    if use_force_playwright:
        logger.info("Force Playwright mode enabled for OhioBuys.")
        rows = await _playwright_scrape_filtered_rows(STATUS_FILTER_LABEL)
        if rows:
            logger.info(f"OhioBuys (Playwright force): scraped {len(rows)} opportunities.")
            return rows
        html = await _playwright_get_browse_html()
        if html:
            rows = _parse_rows_from_html(html)
            rows = _filter_rows_by_status(rows, STATUS_FILTER_LABEL)
            logger.info(f"OhioBuys (Playwright fallback): scraped {len(rows)} opportunities.")
            return rows
        logger.warning("Playwright force mode failed; continuing with HTTP session.")

    session = _create_http_session()

    cookie_str = os.getenv("OHIOBUYS_COOKIES", "").strip()

    if cookie_str:
        _apply_cookie_string(session, cookie_str)
        logger.info("Applied cookies from OHIOBUYS_COOKIES env var.")

    _human_delay()
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
            _human_delay()
            r_get = session.get(ACCESS_CHECK_URL)

        if _is_cloudflare_block(r_get.status_code, r_get.text, dict(r_get.headers)):
            logger.warning("Still blocked. Attempting Playwright fallback...")
            html = await _playwright_get_browse_html()
            if html:
                rows = _parse_rows_from_html(html)
                rows = _filter_rows_by_status(rows, STATUS_FILTER_LABEL)
                logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
                return rows
            return []

    access_html = r_get.text
    soup = BeautifulSoup(access_html, "html.parser")
    logger.info(f"[ACCESS_CHECK] Got {len(access_html)} bytes, status={r_get.status_code}")

    max_attempts = int(os.getenv("OHIOBUYS_MAX_CAPTCHA_ATTEMPTS", "10") or "10")
    filtered_html = ""

    for attempt in range(1, max_attempts + 1):
        logger.info(f"[CAPTCHA ATTEMPT {attempt}/{max_attempts}]")

        raw_payload = _collect_form_fields(soup)
        captcha_html_escaped = _extract_captcha_table_html(access_html)
        guess_info = _empty_guess_info()
        if captcha_html_escaped:
            decoded_info = _decode_captcha_ascii_blocks(captcha_html_escaped)
            char_bitmaps = decoded_info["char_bitmaps"]
            guess_info = _guess_captcha_text_from_bitmaps(char_bitmaps, attempt)
        else:
            logger.warning("Could not locate captcha table in HTML")

        if not _is_confident_captcha_guess(guess_info):
            reason = _guess_rejection_reason(guess_info)
            logger.warning(
                "[CAPTCHA REJECTED] '%s' (%s)",
                guess_info.get("text", ""),
                reason,
            )
            logger.info("Refreshing page to get new captcha...")
            _human_delay()
            r_get = session.get(ACCESS_CHECK_URL)
            if r_get.status_code == 200:
                access_html = r_get.text
                soup = BeautifulSoup(access_html, "html.parser")
                continue
            logger.error("Failed to refresh access_check page")
            break

        captcha_guess = guess_info["text"]
        logger.info(
            "[CAPTCHA ACCEPTED] '%s' (score=%.2f/%.2f)",
            captcha_guess,
            guess_info["total_distance"],
            guess_info["max_total_distance"],
        )

        payload = _massage_payload_for_submit(dict(raw_payload), captcha_guess)

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
        _human_delay()
        r_post = session.post(
            ACCESS_CHECK_URL,
            data=payload,
            headers=post_headers,
            allow_redirects=True,
        )

        logger.info(f"[POST] status={r_post.status_code}, final_url={r_post.url}")

        _human_delay()
        r_browse = session.get(BROWSE_URL, allow_redirects=True)
        logger.info(f"[BROWSE] status={r_browse.status_code}, url={r_browse.url}")

        if r_browse.status_code != 200:
            logger.error(f"Browse page failed with status {r_browse.status_code}")
            continue

        if "access_check" in r_browse.url.lower():
            logger.error("Got redirected back to access_check - captcha was likely wrong!")
            logger.info("Response snippet: " + r_browse.text[:1000])
            _human_delay()
            r_get = session.get(ACCESS_CHECK_URL)
            if r_get.status_code == 200:
                access_html = r_get.text
                soup = BeautifulSoup(access_html, "html.parser")
                continue
            logger.error("Failed to reload access_check after failed submission.")
            break

        browse_soup = BeautifulSoup(r_browse.text, "html.parser")
        filtered_html = _apply_status_filter_to_html(session, browse_soup, STATUS_FILTER_LABEL)
        break

    if not filtered_html:
        logger.error("Failed to solve captcha and reach browse page after all attempts. Trying Playwright...")
        html = await _playwright_get_browse_html()
        if html:
            rows = _parse_rows_from_html(html)
            rows = _filter_rows_by_status(rows, STATUS_FILTER_LABEL)
            logger.info(f"OhioBuys (Playwright): scraped {len(rows)} opportunities.")
            return rows
        return []

    first_page_rows = _parse_rows_from_html(filtered_html)
    page_rows_list: List[List[Dict[str, Any]]] = [
        _filter_rows_by_status(first_page_rows, STATUS_FILTER_LABEL)
    ]

    if _html_has_additional_pages(filtered_html):
        logger.info("Detected multiple pages; attempting pagination via HTTP form posts.")
        extra_pages = _collect_additional_pages(
            session, filtered_html, STATUS_FILTER_LABEL
        )
        if extra_pages:
            page_rows_list.extend(extra_pages)
        elif USE_PLAYWRIGHT_PAGINATION and HAVE_PLAYWRIGHT:
            logger.info("Form-based pagination unavailable; falling back to Playwright pagination.")
            rows = await _playwright_scrape_filtered_rows(STATUS_FILTER_LABEL)
            if rows:
                logger.info(f"OhioBuys (Playwright pagination): scraped {len(rows)} opportunities.")
                return rows
            logger.warning("Playwright pagination failed; returning first page only.")
        elif USE_PLAYWRIGHT_PAGINATION and not HAVE_PLAYWRIGHT:
            logger.info("Playwright pagination requested but playwright is unavailable; using first page only.")

    deduped_rows: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page_rows in page_rows_list:
        for row in page_rows:
            ext_id = row.get("external_id")
            if ext_id and ext_id in seen_ids:
                continue
            if ext_id:
                seen_ids.add(ext_id)
            deduped_rows.append(row)

    for row in deduped_rows:
        row["status"] = _normalize_status_label(row.get("status", ""))

    logger.info(f"OhioBuys: successfully scraped {len(deduped_rows)} opportunities")

    return deduped_rows

 

 

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
