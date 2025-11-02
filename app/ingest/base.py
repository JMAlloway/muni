# app/ingest/base.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class RawOpportunity:
    # ------------------------------------------------------------------
    # Source / identity (ingestor-level metadata)
    # ------------------------------------------------------------------
    source: str                      # e.g. "city_columbus", "franklin_county"
    source_url: str                  # canonical/public URL to the opportunity
    title: str                       # bid title / project name

    # ------------------------------------------------------------------
    # Descriptive / classification
    # ------------------------------------------------------------------
    summary: str = ""                # short blurb for table/email
    description: str = ""            # longer scope / detail text
    category: str = ""               # "construction", "it", etc. (your AI fills this)
    agency_name: str = ""            # e.g. "City of Columbus"
    location_geo: str = ""           # e.g. "Columbus, OH"

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------
    posted_date: Optional[datetime] = None   # what the agency shows
    due_date: Optional[datetime] = None      # what the agency shows
    prebid_date: Optional[datetime] = None   # optional
    # 👇 NEW: when *we* first saw/ingested it (for digests)
    date_added: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Extras
    # ------------------------------------------------------------------
    # most of your ingestors pass a list of URLs, not dicts → make that the default
    attachments: List[str] = field(default_factory=list)
    status: str = "open"
    hash_body: Optional[str] = None

    # ------------------------------------------------------------------
    # IDs / tags
    # ------------------------------------------------------------------
    # e.g. "RFP# 2025-46-19" → "2025-46-19"
    external_id: str = ""
    # you had this in your file – leaving it in
    keyword_tag: str = ""
