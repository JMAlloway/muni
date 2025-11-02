import asyncio
from sqlalchemy import text
from app.db_core import engine

async def wipe():
    async with engine.begin() as conn:
        # SQLite doesn't support TRUNCATE. This just deletes every row.
        await conn.execute(text("DELETE FROM opportunities;"))
    print("Opportunities table cleared (SQLite).")

if __name__ == "__main__":
    asyncio.run(wipe())
