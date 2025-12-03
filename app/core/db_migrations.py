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

            if "first_name" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN first_name TEXT"
                )
            if "last_name" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN last_name TEXT"
                )

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
            if "tier" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'free'"
                )
            if "team_id" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN team_id TEXT"
                )
            if "sms_phone" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN sms_phone TEXT"
                )
            if "sms_opt_in" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN sms_opt_in INTEGER DEFAULT 0"
                )
            if "sms_phone_verified" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN sms_phone_verified INTEGER DEFAULT 0"
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


async def ensure_company_profile_schema(engine) -> None:
    """Ensure company_profiles table exists for AI autofill."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='company_profiles'
                """
            )
            if not res.fetchone():
                await conn.exec_driver_sql(
                    """
                    CREATE TABLE company_profiles (
                        id TEXT PRIMARY KEY,
                        user_id TEXT UNIQUE,
                        data JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
    except Exception:
        return


async def ensure_tracker_team_schema(engine) -> None:
    """Add team_id + visibility to user_bid_trackers for team sharing."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql("PRAGMA table_info('user_bid_trackers')")
            cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}
            if "team_id" not in cols:
                await conn.exec_driver_sql("ALTER TABLE user_bid_trackers ADD COLUMN team_id TEXT")
            if "visibility" not in cols:
                await conn.exec_driver_sql("ALTER TABLE user_bid_trackers ADD COLUMN visibility TEXT DEFAULT 'private'")
    except Exception:
        return


async def ensure_team_schema(engine) -> None:
    """Ensure team tables exist for collaboration features."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='teams'
                """
            )
            if not res.fetchone():
                await conn.exec_driver_sql(
                    """
                    CREATE TABLE teams (
                        id TEXT PRIMARY KEY,
                        name TEXT DEFAULT 'Team',
                        owner_user_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                # Backfill missing created_at column if table exists without it
                res_cols = await conn.exec_driver_sql("PRAGMA table_info('teams')")
                cols: Set[str] = {row._mapping["name"] for row in res_cols.fetchall()}
                if "created_at" not in cols:
                    await conn.exec_driver_sql(
                        "ALTER TABLE teams ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
            res = await conn.exec_driver_sql(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='team_members'
                """
            )
            if not res.fetchone():
                await conn.exec_driver_sql(
                    """
                    CREATE TABLE team_members (
                        id TEXT PRIMARY KEY,
                        team_id TEXT,
                        user_id TEXT,
                        invited_email TEXT,
                        role TEXT DEFAULT 'member',
                        invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        accepted_at TIMESTAMP
                    )
                    """
                )
                await conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)"
                )
            else:
                res_cols = await conn.exec_driver_sql("PRAGMA table_info('team_members')")
                cols: Set[str] = {row._mapping["name"] for row in res_cols.fetchall()}
                if "invited_at" not in cols:
                    await conn.exec_driver_sql(
                        "ALTER TABLE team_members ADD COLUMN invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
            # Ensure unique index on (team_id, invited_email) for conflict checks
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_unique ON team_members(team_id, invited_email)"
            )
            res = await conn.exec_driver_sql(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='bid_notes'
                """
            )
            if not res.fetchone():
                await conn.exec_driver_sql(
                    """
                    CREATE TABLE bid_notes (
                        id TEXT PRIMARY KEY,
                        team_id TEXT,
                        opportunity_id TEXT,
                        author_user_id TEXT,
                        body TEXT,
                        mentions JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_bid_notes_team ON bid_notes(team_id)"
                )
    except Exception:
        return


async def ensure_user_tier_column(engine) -> None:
    """Ensure users.tier exists so billing/webhooks can persist plan."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql("PRAGMA table_info('users')")
            cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}
            if "tier" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'Free'"
                )
    except Exception:
        return


async def ensure_billing_schema(engine) -> None:
    """Add billing-related columns to users table if missing."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql("PRAGMA table_info('users')")
            cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}

            if "stripe_customer_id" not in cols:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
            if "stripe_subscription_id" not in cols:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT")
            if "next_billing_at" not in cols:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN next_billing_at TEXT")
    except Exception:
        # Non-SQLite or insufficient permissions; ignore quietly.
        return
