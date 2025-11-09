# app/init_db_core.py
import asyncio
from sqlalchemy import text
from app.core.db_core import engine
from app.core.models_core import metadata, opportunities

async def init_db_core():
    """
    Create the 'opportunities' table if it does not exist.
    Works for both SQLite (local) and Postgres (Neon/Supabase).
    """
    async with engine.begin() as conn:
        # Create the table safely (if not exists)
        print("Creating tables (if missing)...")
        await conn.run_sync(metadata.create_all)
        print("✅ opportunities table ready.")

        # Optional sanity check
        res = await conn.execute(text("SELECT COUNT(*) FROM opportunities"))
        count = res.scalar()
        print(f"Current rows in opportunities: {count}")

if __name__ == "__main__":
    asyncio.run(init_db_core())
