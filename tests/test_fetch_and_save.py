# app/test_fetch_and_save.py
import asyncio
from datetime import datetime
from sqlalchemy import text
from app.core.db_core import engine
from app.ingest.runner import run_ingestors_once


async def main():
    # --- Count rows before ingestion ---
    async with engine.begin() as conn:
        before = (await conn.execute(text("SELECT COUNT(*) FROM opportunities"))).scalar() or 0

    print(f"🧮 Records before ingest: {before}\n")

    # --- Run all ingestors (mock + city_columbus) ---
    processed = await run_ingestors_once()

    # --- Count rows after ingestion ---
    async with engine.begin() as conn:
        after = (await conn.execute(text("SELECT COUNT(*) FROM opportunities"))).scalar() or 0

    delta = after - before

    print("\n✅ Ingestion complete:")
    print(f"   Total processed (created+updated): {processed}")
    print(f"   New rows added: {delta if delta > 0 else 0}")
    print(f"   Existing rows updated or unchanged: {processed - max(delta, 0)}")
    print(f"   Current total in DB: {after}")

    # --- Show most recent opportunities ---
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT title, agency_name, due_date
                FROM opportunities
                ORDER BY created_at DESC
                LIMIT 5
            """)
        )
        rows = result.fetchall()

    if rows:
        print("\n🆕 Most recent opportunities:")
        for title, agency, due in rows:
            due_str = (
                due.strftime("%Y-%m-%d") if isinstance(due, datetime) and due else "TBD"
            )
            print(f" • {agency}: {title} (Due: {due_str})")
    else:
        print("\n⚠️ No records found in DB.")

    print("\n--- Done ---")


if __name__ == "__main__":
    asyncio.run(main())
