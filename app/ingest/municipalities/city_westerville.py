# app/ingest/municipalities/city_westerville.py

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

import requests

from app.ingest.base import RawOpportunity

AGENCY_NAME = "City of Westerville"
LOCATION = "Westerville, OH"

PORTAL_URL = "https://westerville.bonfirehub.com/portal/?tab=openOpportunities"
OPEN_API_URL = "https://westerville.bonfirehub.com/PublicPortal/getOpenPublicOpportunitiesSectionData"

log = logging.getLogger("city_westerville")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [westerville] %(levelname)s: %(message)s",
)


def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return (
        str(s)
        .replace("\xa0", " ")
        .replace("\u00a0", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _parse_close_dt(ts: Optional[str]) -> Optional[datetime]:
    """
    Westerville DateClose example: "2025-10-28 21:00:00"
    These look like 'YYYY-MM-DD HH:MM:SS' in (most likely) UTC or org-local.
    We'll just treat as naive for now.
    """
    ts = _clean(ts)
    if not ts:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except Exception:
            continue
    return None


def _hash_body(*parts: str) -> str:
    joined = "||".join([p or "" for p in parts])
    return hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()


def _session_with_headers() -> requests.Session:
    """
    Create a browser-y session so Bonfire gives us the same data it gives the portal.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _warm_portal(session: requests.Session) -> None:
    """
    Hit the visible open opportunities tab page to pick up cookies/session.
    """
    log.info("Warm-loading Bonfire portal page...")
    resp = session.get(PORTAL_URL, timeout=30)
    log.info("Warm-load status: %s", resp.status_code)


def _fetch_open_payload(session: requests.Session) -> Dict[str, Any]:
    """
    Mimic the frontend's BFUtil.loadSection('/PublicPortal/getOpenPublicOpportunitiesSectionData').
    We include X-Requested-With to look like an AJAX call.
    """
    ajax_headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": PORTAL_URL,
    }
    resp = session.get(OPEN_API_URL, headers=ajax_headers, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    # Debug snapshot for future troubleshooting
    try:
        with open("westerville_open_debug.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning("Couldn't write debug json: %s", e)

    return data


def _category_from_ref(ref_id: str) -> str:
    u = ref_id.upper()
    if u.startswith("RFP"):
        return "Request for Proposals"
    if u.startswith("RFQ"):
        return "Request for Qualifications"
    if "RFSQ" in u:
        return "Request for Supplier Qualifications"
    if u.startswith("ITB") or "BID" in u:
        return "Bid Solicitation"
    return ""


def _status_from_projectstatusid(status_id: str) -> str:
    """
    ProjectStatusID "2" in your payload is clearly "Open".
    We'll mark anything else not '2' as 'closed'.
    """
    status_id = _clean(status_id)
    if status_id == "2":
        return "open"
    return "closed"


def _project_to_raw(proj: Dict[str, Any]) -> RawOpportunity:
    """
    Convert one project dict from payload["projects"][<id>] to RawOpportunity.
    The keys we saw in your payload were:
      - ProjectID
      - ReferenceID
      - ProjectStatusID
      - ProjectName
      - DateClose
    """
    project_id = _clean(proj.get("ProjectID"))
    ref_id = _clean(proj.get("ReferenceID"))
    status_id = _clean(proj.get("ProjectStatusID"))
    title = _clean(proj.get("ProjectName"))
    close_ts = _clean(proj.get("DateClose"))

    detail_url = f"https://westerville.bonfirehub.com/opportunities/{project_id}" if project_id else PORTAL_URL
    due_dt = _parse_close_dt(close_ts)
    status_text = _status_from_projectstatusid(status_id)
    category = _category_from_ref(ref_id)

    # summary (for your card UI)
    summary = f"Closes {close_ts}" if close_ts else ""

    hb = _hash_body(
        ref_id,
        title,
        close_ts,
        project_id,
        status_text,
    )

    external_id = ref_id or project_id or hb[:16]

    return RawOpportunity(
        source="city_westerville",
        source_url=detail_url,
        title=title or "City of Westerville Opportunity",
        summary=summary,
        description=title or ref_id or "City of Westerville Opportunity",
        category=category,
        agency_name=AGENCY_NAME,
        location_geo=LOCATION,
        posted_date=None,
        due_date=due_dt,
        prebid_date=None,
        attachments=None,
        status=status_text,
        hash_body=hb,
        external_id=external_id,
        keyword_tag=category,
    )


def fetch_sync() -> List[RawOpportunity]:
    log.info("Westerville Bonfire scrape (final structured) starting...")

    session = _session_with_headers()
    _warm_portal(session)

    data = _fetch_open_payload(session)

    # Shape we saw:
    # {
    #   "success": 1,
    #   "message": "Success",
    #   "payload": {
    #       "projects": {
    #           "204659": {...},
    #           "203189": {...},
    #           ...
    #       },
    #       "departments": []
    #   }
    # }
    projects_obj = {}
    if isinstance(data, dict):
        payload = data.get("payload", {})
        if isinstance(payload, dict):
            projects_obj = payload.get("projects", {}) or {}

    if not isinstance(projects_obj, dict):
        log.warning("Did not find payload.projects as a dict.")
        projects_obj = {}

    log.info("Open opportunities payload has %d project(s) before mapping", len(projects_obj))

    items: List[RawOpportunity] = []
    for proj_id, proj in projects_obj.items():
        if not isinstance(proj, dict):
            continue
        try:
            items.append(_project_to_raw(proj))
        except Exception as e:
            log.warning("Failed to map project %s (%s): %s", proj_id, proj, e)

    log.info("Parsed %d Westerville opportunities from Bonfire payload", len(items))
    return items


async def fetch() -> List[RawOpportunity]:
    return await asyncio.to_thread(fetch_sync)
