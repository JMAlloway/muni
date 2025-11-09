# app/db_core.py

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import settings
from app.core.models_core import opportunities

# centralized classifier (rule -> shortlist -> LLM -> floors)
from app.ai.categorizer import classify_opportunity
from app.ai.taxonomy import normalize_category_name

# Example DSN: postgresql+psycopg://user:password@host/dbname
engine = create_async_engine(settings.DB_URL, echo=False, future=True)


def _ensure_ai_category(raw) -> None:
    """
    Make sure `raw` has a good, human-readable category and a confidence.

    Priority:
    1. If ingestor set a category -> normalize it & set ai_category too.
    2. Else -> run the shared classifier on title + description/summary.
    """
    # 1) ingestor already set something
    if getattr(raw, "category", None):
        nice = normalize_category_name(raw.category)
        raw.category = nice
        # keep ai_... in sync
        if not getattr(raw, "ai_category", None):
            raw.ai_category = nice
        if not getattr(raw, "ai_confidence", None):
            raw.ai_confidence = 0.90
        return

    # 2) no category -> classify
    title = getattr(raw, "title", "") or ""
    desc = getattr(raw, "description", None) or getattr(raw, "summary", None)

    cls = classify_opportunity(title, desc)
    cat = cls.get("category") or "Other / Miscellaneous"
    conf = cls.get("confidence") or 0.55

    raw.category = cat
    raw.ai_category = cat
    raw.ai_confidence = conf


async def save_opportunities(batch):
    """
    Bulk insert/update using SQLAlchemy Core.
    De-duplicates on source_url (unique constraint).
    Ensures date_added is set only once (on first insert).
    """
    if not batch:
        return 0

    async with engine.begin() as conn:
        for raw in batch:
            # make sure we have a category set (centralized AI step!)
            try:
                _ensure_ai_category(raw)
            except Exception:
                # hard fallback — do not block saving
                raw.category = "Other / Miscellaneous"
                raw.ai_category = "Other / Miscellaneous"
                raw.ai_confidence = 0.51

            # fallback if ingestor forgot to set it
            date_added = getattr(raw, "date_added", None) or datetime.now(timezone.utc)

            stmt = (
                insert(opportunities)
                .values(
                    source=raw.source,
                    source_url=raw.source_url,
                    title=raw.title,
                    summary=raw.summary,
                    full_text=getattr(raw, "description", None),

                    # AI / taxonomy fields (centralized)
                    category=raw.category,
                    ai_category=getattr(raw, "ai_category", raw.category),
                    ai_confidence=getattr(raw, "ai_confidence", 0.9),

                    external_id=getattr(raw, "external_id", None),
                    keyword_tag=getattr(raw, "keyword_tag", None),

                    agency_name=raw.agency_name,
                    location_geo=raw.location_geo,

                    posted_date=raw.posted_date,
                    due_date=raw.due_date,
                    prebid_date=raw.prebid_date,

                    attachments=raw.attachments,
                    status=raw.status,
                    hash_body=raw.hash_body,

                    # timestamps
                    date_added=date_added,
                    last_seen=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["source_url"],
                    set_={
                        # ❌ never overwrite date_added
                        "title": raw.title,
                        "summary": raw.summary,
                        "full_text": getattr(raw, "description", None),

                        # re-apply AI category — if we improve the classifier,
                        # the next ingest will refresh it
                        "category": raw.category,
                        "ai_category": getattr(raw, "ai_category", raw.category),
                        "ai_confidence": getattr(raw, "ai_confidence", 0.9),

                        "external_id": getattr(raw, "external_id", None),
                        "keyword_tag": getattr(raw, "keyword_tag", None),

                        "due_date": raw.due_date,
                        "hash_body": raw.hash_body,
                        "updated_at": text("CURRENT_TIMESTAMP"),
                        "last_seen": text("CURRENT_TIMESTAMP"),
                    },
                )
            )

            await conn.execute(stmt)

    return len(batch)
