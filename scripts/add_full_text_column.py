import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.db_core import engine

async def main():
    async with engine.begin() as conn:
        try:
            # First try Postgres / normal path
            await conn.execute(text("""
                ALTER TABLE opportunities
                ADD COLUMN IF NOT EXISTS full_text TEXT;
            """))
            print("✅ Column added with IF NOT EXISTS (Postgres style).")

        except OperationalError:
            # Fallback for SQLite (no IF NOT EXISTS support)
            print("ℹ️ Falling back to SQLite-style ALTER (no IF NOT EXISTS).")
            try:
                await conn.execute(text("""
                    ALTER TABLE opportunities
                    ADD COLUMN full_text TEXT;
                """))
                print("✅ Column added with plain ADD COLUMN (SQLite style).")
            except OperationalError as e2:
                # Likely 'duplicate column name' or similar -> means column already there
                print(f"⚠️ Skipped adding column. Probably already exists. Detail: {e2}")

    print("Done.")

asyncio.run(main())
