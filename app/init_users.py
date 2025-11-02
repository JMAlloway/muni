import asyncio
from datetime import datetime
from sqlalchemy import text
from app.db import AsyncSessionLocal

DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    digest_frequency TEXT NOT NULL DEFAULT 'daily',  -- 'daily', 'weekly', 'none'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SEED_USER = """
INSERT OR IGNORE INTO users (email, digest_frequency, created_at)
VALUES (:email, :freq, :created_at)
"""

async def init_users():
    async with AsyncSessionLocal() as session:
        # 1. create the users table if it doesn't exist
        await session.execute(text(DDL_USERS))

        # 2. add a default user (your test address)
        await session.execute(
            text(SEED_USER),
            {
                "email": "admin@example.com",
                "freq": "daily",
                "created_at": datetime.utcnow(),
            },
        )

        # 3. commit changes
        await session.commit()

        # 4. sanity check
        result = await session.execute(text("SELECT id, email, digest_frequency FROM users"))
        rows = result.fetchall()
        print("Current users:")
        for row in rows:
            print("  ", row)

if __name__ == "__main__":
    asyncio.run(init_users())
