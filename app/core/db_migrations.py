from typing import Set


async def ensure_uploads_schema(engine) -> None:
    """Lightweight, idempotent migration for user_uploads table.

    Adds missing columns that newer code expects but old local SQLite DBs
    might not have (e.g., 'mime'). Uses simple PRAGMA inspection so it
    works on SQLite without alembic.
    """
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql("PRAGMA table_info('user_uploads')")
            cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}

            if "mime" not in cols:
                await conn.exec_driver_sql("ALTER TABLE user_uploads ADD COLUMN mime TEXT")
            if "storage_key" not in cols:
                # Required for locating files (S3 key or local path)
                await conn.exec_driver_sql("ALTER TABLE user_uploads ADD COLUMN storage_key TEXT")
            if "size" not in cols:
                await conn.exec_driver_sql("ALTER TABLE user_uploads ADD COLUMN size INTEGER DEFAULT 0")
            if "created_at" not in cols:
                # store as TEXT timestamp by default for SQLite compatibility
                await conn.exec_driver_sql("ALTER TABLE user_uploads ADD COLUMN created_at TEXT DEFAULT (datetime('now'))")

            # Future-proof: add optional fields if missing
            if "version" not in cols:
                await conn.exec_driver_sql("ALTER TABLE user_uploads ADD COLUMN version INTEGER DEFAULT 1")
            if "source_note" not in cols:
                await conn.exec_driver_sql("ALTER TABLE user_uploads ADD COLUMN source_note TEXT DEFAULT 'user-upload'")
    except Exception:
        # Non-SQLite or missing table; ignore quietly.
        return


async def ensure_onboarding_schema(engine) -> None:
    """Ensure onboarding-related columns/tables exist."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql("PRAGMA table_info('users')")
            cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}

            if "primary_interest" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN primary_interest TEXT DEFAULT 'everything'"
                )
            if "onboarding_step" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN onboarding_step TEXT DEFAULT 'signup'"
                )
            if "onboarding_completed" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0"
                )
            if "first_tracked_at" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN first_tracked_at TIMESTAMP"
                )

            res = await conn.exec_driver_sql(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='user_onboarding_events'
                """
            )
            if not res.fetchone():
                await conn.exec_driver_sql(
                    """
                    CREATE TABLE user_onboarding_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_email TEXT NOT NULL,
                        step TEXT NOT NULL,
                        metadata JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.exec_driver_sql(
                    "CREATE INDEX idx_onboarding_events_email ON user_onboarding_events(user_email)"
                )
    except Exception:
        # Non-SQLite or insufficient permissions; ignore quietly.
        return
