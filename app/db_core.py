# app/db_core.py
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text
from app.settings import settings
from app.models_core import opportunities
from datetime import datetime, timezone

# Example DSN: postgresql+psycopg://user:password@host/dbname
engine = create_async_engine(settings.DB_URL, echo=False, future=True)


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

                    category=raw.category,
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

                    # 👇 NEW
                    date_added=getattr(raw, "date_added", datetime.now(timezone.utc)),
                    last_seen=datetime.now(timezone.utc),  # 👈 NEW
                )
                .on_conflict_do_update(
                    index_elements=["source_url"],
                    set_={
                        # ❌ never overwrite date_added
                        "title": raw.title,
                        "summary": raw.summary,
                        "full_text": getattr(raw, "description", None),

                        "category": raw.category,
                        "external_id": getattr(raw, "external_id", None),
                        "keyword_tag": getattr(raw, "keyword_tag", None),

                        "due_date": raw.due_date,
                        "hash_body": raw.hash_body,
                        "updated_at": text("CURRENT_TIMESTAMP"),
                        "last_seen": text("CURRENT_TIMESTAMP"),  # 👈 refresh each ingest
                    },
                )
            )

            await conn.execute(stmt)

    return len(batch)
