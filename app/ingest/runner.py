# app/ingest/runner.py

import inspect
import hashlib
from typing import List

from app.ingest import mock_ingestor
from app.ingest.municipalities import city_columbus
from app.ingest.municipalities import city_grove_city
from app.ingest.municipalities import city_gahanna
from app.ingest.municipalities import city_marysville
from app.ingest.municipalities import city_whitehall
from app.ingest.municipalities import city_worthington
from app.ingest.municipalities import city_grandview_heights
from app.ingest.municipalities import swaco
from app.ingest.municipalities import cota
from app.ingest.municipalities import franklin_county
from app.ingest.municipalities import city_westerville
from app.ingest.municipalities import columbus_metropolitan_library
from app.ingest.municipalities import cmha
from app.ingest.municipalities import metro_parks
from app.ingest.municipalities import columbus_airports
from app.ingest.municipalities import morpc
from app.ingest.municipalities import dublin_city_schools
from app.ingest.municipalities import minerva_park
from app.ingest.municipalities import city_new_albany
from app.ingest.municipalities import ohiobuys  # <-- NEW

from app.db_core import save_opportunities


# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------

class RowAdapter:
    """
    Wrap a dict so save_opportunities() can access row.source, row.title, etc.
    Also allows setting attributes like row.hash_body which writes back to dict.
    """
    def __init__(self, data: dict):
        super().__setattr__("_data", data)

    def __getattr__(self, item):
        try:
            return self._data[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self._data[key] = value

    def to_dict(self):
        return self._data


def hash_parts(*parts: str) -> str:
    """Simple hash used to detect content changes."""
    joined = "|".join((p or "").lower().strip() for p in parts if p is not None)
    return hashlib.sha256(joined.encode()).hexdigest()


async def _collect_from_ingestor(fn) -> List:
    """Call either a sync or async fetch() and return list of row dicts/objects."""
    if inspect.iscoroutinefunction(fn):
        return await fn()
    return fn()


# ------------------------------------------------------------------------------------
# Main entrypoint
# ------------------------------------------------------------------------------------

async def run_ingestors_once() -> int:
    """
    Run all registered ingestors and save results to DB.
    Returns total number of items processed (created or updated).
    """

    sources = [
        # mock_ingestor.fetch,
        # city_columbus.fetch,
        # city_grove_city.fetch,
        # city_gahanna.fetch,
        # city_marysville.fetch,
        # city_whitehall.fetch,
        # city_worthington.fetch,
        # city_grandview_heights.fetch,
        # swaco.fetch,
        # cota.fetch,
        # franklin_county.fetch,
        # city_westerville.fetch,
        # columbus_metropolitan_library.fetch,
        # cmha.fetch,
        # metro_parks.fetch,
        # columbus_airports.fetch,
        # morpc.fetch,
        # dublin_city_schools.fetch,
        # minerva_park.fetch,
        # city_new_albany.fetch,
        ohiobuys.fetch,  # <-- currently just OhioBuys enabled
    ]

    total = 0

    for fetch_fn in sources:
        name = getattr(fetch_fn, "__module__", str(fetch_fn))
        print(f"Running ingestor: {name}")

        try:
            batch = await _collect_from_ingestor(fetch_fn)
        except Exception as e:
            print(f"[WARN] Ingestor {name} failed: {e}")
            batch = []

        if not batch:
            print(f"[INFO] Ingestor {name} returned no results.")
            continue

        # normalize each row and ensure hash_body + required fields exist
        normalized_rows = []
        for r in batch:
            if isinstance(r, dict):
                # Make sure all required fields exist before DB save_opportunities()
                r.setdefault("source", "")
                r.setdefault("source_url", "")
                r.setdefault("title", "")
                r.setdefault("summary", "")
                r.setdefault("full_text", "")
                r.setdefault("category", "")
                r.setdefault("external_id", "")
                r.setdefault("keyword_tag", None)
                r.setdefault("agency_name", "")
                r.setdefault("location_geo", "")
                r.setdefault("posted_date", None)
                r.setdefault("due_date", None)
                r.setdefault("prebid_date", None)
                r.setdefault("attachments", [])
                r.setdefault("status", "open")
                # build/ensure hash_body
                title_val = r.get("title") or ""
                desc_val = (
                    r.get("full_text")
                    or r.get("summary")
                    or ""
                )
                due_val = r.get("due_date")
                hash_val = r.get("hash_body")
                if not hash_val:
                    hash_val = hash_parts(title_val, desc_val, str(due_val))
                r["hash_body"] = hash_val

                normalized_rows.append(RowAdapter(r))

            else:
                # object style (older ingestors)
                if not hasattr(r, "keyword_tag"):
                    setattr(r, "keyword_tag", None)
                if not hasattr(r, "location_geo"):
                    setattr(r, "location_geo", "")
                if not hasattr(r, "prebid_date"):
                    setattr(r, "prebid_date", None)
                if not hasattr(r, "attachments"):
                    setattr(r, "attachments", [])

                title_val = getattr(r, "title", "") or ""
                desc_val = (
                    getattr(r, "full_text", "")
                    or getattr(r, "summary", "")
                    or getattr(r, "description", "")
                    or ""
                )
                due_val = getattr(r, "due_date", None)

                hash_val = getattr(r, "hash_body", None)
                if not hash_val:
                    hash_val = hash_parts(title_val, desc_val, str(due_val))
                    setattr(r, "hash_body", hash_val)

                normalized_rows.append(r)

        saved = await save_opportunities(normalized_rows)
        print(f"[OK] Ingestor {name} processed {saved} rows.")
        total += saved

    print(f"✅ Completed ingestion run. Total processed: {total}")
    return total


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_ingestors_once())
