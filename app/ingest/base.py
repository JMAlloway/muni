# app/ingest/base.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class RawOpportunity:
    # source metadata
    source: str                        # e.g. "city_columbus"
    source_url: str                    # canonical link or hash back to source portal
    title: str                         # bid title / project name

    # descriptive text
    summary: str = ""                  # short blurb or department
    description: str = ""              # long body/scope text
    category: str = ""                 # we'll surface this as "Type" in UI
    agency_name: str = ""              # e.g. "City of Columbus"
    location_geo: str = ""             # e.g. "Columbus, OH"

    # dates
    posted_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    prebid_date: Optional[datetime] = None

    # extras
    attachments: list[dict] | None = None
    status: str = "open"
    hash_body: str | None = None

    # NEW: Solicitation # / RFQ / external reference ID
    external_id: str = ""              # e.g. "RFQ031521"
    keyword_tag: str = ""   # <-- NEW
