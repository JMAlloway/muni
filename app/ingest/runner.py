# app/ingest/runner.py
import json
import inspect
import hashlib
from typing import List, Set, Optional
from sqlalchemy import text
import asyncio
from sqlalchemy import text

# --- AI imports ---------------------------------------------------------------
from app.ai.classifier import classify_opportunity
from app.ai.extract_fields import extract_key_fields
from app.ai.client import get_llm_client

# these two are NEW but optional
try:
    from app.ai.summarize_scope import summarize_scope
except Exception:
    summarize_scope = None

try:
    from app.ai.auto_tags import auto_tags_from_blob
except Exception:
    auto_tags_from_blob = None

LLM_CLIENT = get_llm_client()

# --- Ingestors ----------------------------------------------------------------
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
from app.ingest.municipalities import cota_improved
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
from app.ingest.municipalities import ohiobuys  # new
from app.core.db_core import save_opportunities, engine


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

async def close_missing_opportunities():
    async with engine.begin() as conn:
        # 1️⃣ get distinct agency names
        result = await conn.execute(
            text("SELECT DISTINCT agency_name FROM opportunities WHERE agency_name IS NOT NULL;")
        )
        agencies = [r[0] for r in result.fetchall() if r[0]]

        print(f"Found {len(agencies)} agencies to check…")

        # 2️⃣ loop through each and mark stale as closed
        for agency in agencies:
            await conn.execute(
                text("""
                    UPDATE opportunities
                    SET status = 'closed'
                    WHERE agency_name = :agency
                      AND status = 'open'
                      AND (last_seen IS NULL OR last_seen < datetime('now', '-1 day'));
                """),
                {"agency": agency},
            )
            print(f"✅ Checked {agency}")

    print("🎯 Done marking missing RFPs as closed.")


# ---- for local testing ----
if __name__ == "__main__":
    asyncio.run(close_missing_opportunities())

# we'll cache the table columns so we only check once
_OPP_COLUMNS: Optional[Set[str]] = None


async def _get_opportunity_columns(conn) -> Set[str]:
    """
    Try to discover available columns on the 'opportunities' table.
    Works for SQLite (PRAGMA) and falls back to INFORMATION_SCHEMA for Postgres.
    We keep it flexible so the rest of the code can be additive.
    """
    global _OPP_COLUMNS
    if _OPP_COLUMNS is not None:
        return _OPP_COLUMNS

    cols: Set[str] = set()

    # 1) try SQLite style
    try:
        res = await conn.execute(text("PRAGMA table_info(opportunities)"))
        rows = res.fetchall()
        if rows:
            for r in rows:
                # sqlite returns: cid, name, type, notnull, dflt_value, pk
                name = r[1]
                cols.add(name)
    except Exception:
        pass

    # 2) try Postgres / others
    if not cols:
        try:
            res = await conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'opportunities'
                    """
                )
            )
            rows = res.fetchall()
            for r in rows:
                cols.add(r[0])
        except Exception:
            pass

    _OPP_COLUMNS = cols
    return cols


async def ai_enrich_opportunity(conn, external_id: str, agency_name: str) -> bool:
    """
    Enrich a newly inserted/updated opportunity with AI metadata.
    """
    res = await conn.execute(
        text("""
            SELECT id, title, agency_name, description, full_text
            FROM opportunities
            WHERE external_id = :ext_id
              AND agency_name = :agency
            LIMIT 1
        """),
        {"ext_id": external_id, "agency": agency_name},
    )
    row = res.mappings().first()
    if not row:
        return False

    # 👉 this is the field you said has the full description
    title = row.get("title") or ""
    agency = row.get("agency_name") or ""
    summary = row.get("summary") or ""
    desc = summary or row.get("description") or ""
    full_text = row.get("full_text") or ""
    combined_blob = " ".join([p for p in (full_text, desc, summary, title) if p])

    # prefer the longest/most detailed text we have
    blob = full_text or desc or title

    # --- existing AI ---------------------------------------------------------
    cat, conf = classify_opportunity(
        title=title,
        agency=agency,
        description=blob,
        llm_client=LLM_CLIENT,   # plug in OpenAI later
    )
    fields = extract_key_fields(blob, llm_client=LLM_CLIENT)

    # --- NEW: optional summary + tags ----------------------------------------
    # only run these if the helpers are actually importable
    ai_summary = ""
    ai_tags = []
    if summarize_scope is not None:
        ai_summary = summarize_scope(
            title=title,
            description=desc,
            full_text=full_text,
            llm_client=LLM_CLIENT,
        ) or ""
    if auto_tags_from_blob is not None:
        ai_tags = auto_tags_from_blob(
            title=title,
            description=desc,
            full_text=combined_blob,
            llm_client=LLM_CLIENT,
        ) or []
        # fallback: if still empty and we have a summary, try summary-only to squeeze matches
        if not ai_tags and summary:
            ai_tags = auto_tags_from_blob(
                title=title,
                description=summary,
                full_text=summary,
                llm_client=LLM_CLIENT,
            ) or []

    # If we found strong specialty tags, let them override an empty/other category.
    if ai_tags and (not cat or cat == "other"):
        cat = ai_tags[0]
        conf = 0.9

    print(
        f"[AI] title={title[:120]!r} | agency={agency!r} | ext={external_id!r} "
        f"| cat={cat} | conf={conf} | fields={fields} | tags={ai_tags}"
    )

    # figure out which columns we actually have
    cols = await _get_opportunity_columns(conn)

    # baseline update (what you had)
    await conn.execute(
        text("""
            UPDATE opportunities
            SET
                ai_category = :cat,
                ai_category_conf = :conf,
                ai_fields_json = :fields_json,
                ai_version = :ver
            WHERE id = :id
        """),
        {
            "cat": cat or "other",
            "conf": conf or 0.0,
            "fields_json": json.dumps(fields),
            "ver": "v1.0",
            "id": row["id"],
        },
    )

    # additive update if columns exist
    if "ai_summary" in cols or "ai_tags_json" in cols:
        await conn.execute(
            text("""
                UPDATE opportunities
                SET
                    ai_summary = CASE WHEN :summary IS NULL THEN ai_summary ELSE :summary END,
                    ai_tags_json = CASE WHEN :tags_json IS NULL THEN ai_tags_json ELSE :tags_json END,
                    ai_version = :ver
                WHERE id = :id
            """),
            {
                "summary": ai_summary if "ai_summary" in cols else None,
                "tags_json": json.dumps(ai_tags) if "ai_tags_json" in cols else None,
                "ver": "v1.1",
                "id": row["id"],
            },
        )

    return True


class RowAdapter:
    """Wrap a dict so save_opportunities() can access row.source, etc."""
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


# ------------------------------------------------------------------------------
# Main entrypoint
# ------------------------------------------------------------------------------

async def run_ingestors_once() -> int:
    """
    Run all registered ingestors and save results to DB.
    Returns total number of items processed (created or updated).
    """

    sources = [
         #mock_ingestor.fetch,
         #city_columbus.fetch,
         #city_grove_city.fetch,
         #city_gahanna.fetch,
         #city_marysville.fetch,
         #city_whitehall.fetch,
         #city_worthington.fetch,
         #city_grandview_heights.fetch,
         #swaco.fetch,
         #cota.fetch,
         cota_improved.fetch,
         #franklin_county.fetch,
         #city_westerville.fetch,
         #columbus_metropolitan_library.fetch,
         #cmha.fetch,
         #metro_parks.fetch,
         #columbus_airports.fetch,
         #morpc.fetch,
         #dublin_city_schools.fetch,
         #minerva_park.fetch,
         #city_new_albany.fetch,
         #ohiobuys.fetch,
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

        normalized_rows = []
        for r in batch:
            if isinstance(r, dict):
                # Ensure required fields exist
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

                title_val = r.get("title") or ""
                desc_val = r.get("full_text") or r.get("summary") or ""
                due_val = r.get("due_date")
                hash_val = r.get("hash_body")
                if not hash_val:
                    hash_val = hash_parts(title_val, desc_val, str(due_val))
                r["hash_body"] = hash_val

                normalized_rows.append(RowAdapter(r))
            else:
                # object-style record
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

        # --- AI enrichment step (for new/updated records) ---------------------
        async with engine.begin() as conn:
            cols = await _get_opportunity_columns(conn)  # warm cache once per loop
            for r in batch:
                ext_id = r.get("external_id") if isinstance(r, dict) else getattr(r, "external_id", "")
                agency = r.get("agency_name") if isinstance(r, dict) else getattr(r, "agency_name", "")
                updated = False
                if ext_id and agency:
                    updated = await ai_enrich_opportunity(conn, ext_id, agency)
                if not updated:
                    # ✅ NEW: fallback so these rows don't stay NULL
                    title = r.get("title") if isinstance(r, dict) else getattr(r, "title", "")
                    summary = r.get("summary") if isinstance(r, dict) else getattr(r, "summary", "")
                    desc = (
                        (r.get("full_text") if isinstance(r, dict) else getattr(r, "full_text", ""))
                        or summary
                        or (r.get("description") if isinstance(r, dict) else getattr(r, "description", ""))
                        or title
                    )
                    combined_blob = " ".join([p for p in (
                        r.get("full_text") if isinstance(r, dict) else getattr(r, "full_text", ""),
                        summary,
                        desc,
                        title,
                    ) if p])
                    hash_body = r.get("hash_body") if isinstance(r, dict) else getattr(r, "hash_body", "")
                    blob = desc or title

                    cat, conf = classify_opportunity(
                        title=title or "",
                        agency=agency or "",
                        description=blob,
                        llm_client=LLM_CLIENT,
                    )
                    fields = extract_key_fields(blob, llm_client=LLM_CLIENT)

                    # optional summary/tags
                    ai_summary = ""
                    ai_tags = []
                    if summarize_scope is not None:
                        ai_summary = summarize_scope(
                            title=title or "",
                            description=desc or "",
                            full_text=blob or "",
                            llm_client=LLM_CLIENT,
                        ) or ""
                    if auto_tags_from_blob is not None:
                        ai_tags = auto_tags_from_blob(
                            title=title or "",
                            description=desc or "",
                            full_text=combined_blob or "",
                            llm_client=LLM_CLIENT,
                        ) or []
                        if not ai_tags and summary:
                            ai_tags = auto_tags_from_blob(
                                title=title or "",
                                description=summary or "",
                                full_text=summary or "",
                                llm_client=LLM_CLIENT,
                            ) or []

                    # Use specialty tags to set category when we otherwise have "other"/none.
                    if ai_tags and (not cat or cat == "other"):
                        cat = ai_tags[0]
                        conf = 0.9

                    # baseline update (what you had)
                    await conn.execute(
                        text("""
                            UPDATE opportunities
                            SET
                                ai_category = :cat,
                                ai_category_conf = :conf,
                                ai_fields_json = :fields_json,
                                ai_version = :ver
                            WHERE title = :title
                              AND (:hash IS NULL OR :hash = '' OR hash_body = :hash)
                        """),
                        {
                            "cat": cat or "other",
                            "conf": float(conf or 0.0),
                            "fields_json": json.dumps(fields),
                            "ver": "v1.0",
                            "title": title or "",
                            "hash": (hash_body or None),
                        },
                    )

                    # additive update if columns exist
                    if "ai_summary" in cols or "ai_tags_json" in cols:
                        await conn.execute(
                            text("""
                                UPDATE opportunities
                                SET
                                    ai_summary = CASE WHEN :summary IS NULL THEN ai_summary ELSE :summary END,
                                    ai_tags_json = CASE WHEN :tags_json IS NULL THEN ai_tags_json ELSE :tags_json END,
                                    ai_version = :ver
                                WHERE title = :title
                                  AND (:hash IS NULL OR :hash = '' OR hash_body = :hash)
                            """),
                            {
                                "summary": ai_summary if "ai_summary" in cols else None,
                                "tags_json": json.dumps(ai_tags) if "ai_tags_json" in cols else None,
                                "ver": "v1.1",
                                "title": title or "",
                                "hash": (hash_body or None),
                            },
                        )

    print(f"✅ Completed ingestion run. Total processed: {total}")
    return total


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_ingestors_once())

