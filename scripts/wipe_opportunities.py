import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.db_core import engine

async def wipe():
    async with engine.begin() as conn:
        # SQLite doesn't support TRUNCATE. This just deletes every row.
        await conn.execute(text("DELETE FROM opportunities;"))
    print("Opportunities table cleared (SQLite).")

if __name__ == "__main__":
    asyncio.run(wipe())
