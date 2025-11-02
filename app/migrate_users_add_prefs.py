import asyncio
import json
from datetime import datetime
from sqlalchemy import text
from app.db import AsyncSessionLocal

ALTER_USERS_TABLES = [
    # Add digest_frequency if it doesn't exist
    """
    ALTER TABLE users
    ADD COLUMN digest_frequency TEXT NOT NULL DEFAULT 'daily';
    """,
    # Add agency_filter if it doesn't exist
    """
    ALTER TABLE users
    ADD COLUMN agency_filter TEXT DEFAULT '[]';
    """
]

UPSERT_USER = """
INSERT OR IGNORE INTO users (email, digest_frequency, agency_filter, created_at)
VALUES (:email, :freq, :agencies, :created_at)
"""

UPDATE_USER = """
UPDATE users
SET digest_frequency = :freq,
    agency_filter = :agencies
WHERE email = :email
"""

async def migrate():
    async with AsyncSessionLocal() as session:
        # Try each ALTER TABLE, but ignore if column already exists.
        for stmt in ALTER_USERS_TABLES:
            try:
                await session.execute(text(stmt))
            except Exception as e:
                # SQLite will error if column already exists.
                print(f"[migrate] skipping column add (maybe exists): {e}")

        # seed or update a test user with preferences
        email = "admin@example.com"  # change if you want your own
        freq = "daily"               # could be 'daily', 'weekly', 'none'
        agencies = json.dumps(["City of Columbus", "Delaware County"])

        # First try insert with IGNORE
        await session.execute(
            text(UPSERT_USER),
            {
                "email": email,
                "freq": freq,
                "agencies": agencies,
                "created_at": datetime.utcnow(),
            },
        )

        # Then force update to ensure prefs match what we want
        await session.execute(
            text(UPDATE_USER),
            {
                "email": email,
                "freq": freq,
                "agencies": agencies,
            },
        )

        await session.commit()

        # sanity check print
        res = await session.execute(
            text("SELECT id, email, digest_frequency, agency_filter FROM users")
        )
        rows = res.fetchall()
        print("Users after migration:")
        for row in rows:
            print(" ", row)

if __name__ == "__main__":
    asyncio.run(migrate())
