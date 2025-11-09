# app/migrate_users_auth.py

import asyncio
from sqlalchemy import text
from app.core.db import AsyncSessionLocal

async def migrate():
    async with AsyncSessionLocal() as session:
        # add password_hash column
        try:
            await session.execute(
                text("""
                    ALTER TABLE users
                    ADD COLUMN password_hash TEXT
                """)
            )
            print("[migrate_users_auth] added password_hash")
        except Exception as e:
            print("[migrate_users_auth] skipping password_hash:", e)

        # add is_active column
        try:
            await session.execute(
                text("""
                    ALTER TABLE users
                    ADD COLUMN is_active INTEGER DEFAULT 1
                """)
            )
            print("[migrate_users_auth] added is_active")
        except Exception as e:
            print("[migrate_users_auth] skipping is_active:", e)

        await session.commit()

    print("[migrate_users_auth] done.")

if __name__ == "__main__":
    asyncio.run(migrate())
