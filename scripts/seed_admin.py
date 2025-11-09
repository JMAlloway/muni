"""Seed a default administrator account."""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.db import AsyncSessionLocal
from app.security import hash_password
from app.core.settings import settings

async def main():
    email = settings.ADMIN_EMAIL
    pw    = settings.ADMIN_PASSWORD
    hpw   = hash_password(pw)
    async with AsyncSessionLocal() as s:
        await s.execute(text("""
            INSERT INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at)
            VALUES (:email, :pw, 'daily', '[]', 1, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET
              password_hash = excluded.password_hash,
              is_active = 1
        """), {"email": email, "pw": hpw})
        await s.commit()
    print("Seeded admin:", email)

if __name__ == "__main__":
    asyncio.run(main())
