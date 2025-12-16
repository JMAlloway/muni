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


async def ensure_opportunity_scope_columns(engine) -> None:
    """Ensure opportunities tables have summary + scope_of_work columns.

    Works for both SQLite (via PRAGMA) and Postgres (via IF NOT EXISTS).
    Covers both legacy table names: opportunities (core) and opportunity (ORM).
    """
    try:
        async with engine.begin() as conn:
            dialect = getattr(conn.engine, "dialect", None)
            dialect_name = getattr(dialect, "name", "unknown") if dialect else "unknown"

            for table in ("opportunities", "opportunity"):
                try:
                    if dialect_name == "sqlite":
                        res = await conn.exec_driver_sql(f"PRAGMA table_info('{table}')")
                        cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}
                        if not cols:
                            continue  # table missing
                        if "summary" not in cols:
                            await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN summary TEXT")
                        if "scope_of_work" not in cols:
                            await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN scope_of_work TEXT")
                    else:
                        await conn.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS summary TEXT"
                        )
                        await conn.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS scope_of_work TEXT"
                        )
                except Exception:
                    # Table might not exist in this database; skip quietly
                    continue
    except Exception:
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


async def ensure_knowledge_base_schema(engine) -> None:
    """Create knowledge base + RFP response tables if missing (SQLite-friendly)."""
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    team_id TEXT,
                    filename TEXT NOT NULL,
                    mime TEXT,
                    size INTEGER,
                    storage_key TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    tags JSON,
                    extracted_text TEXT,
                    extraction_status TEXT DEFAULT 'pending',
                    extraction_error TEXT,
                    has_embeddings INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_kdocs_user ON knowledge_documents(user_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_kdocs_team ON knowledge_documents(team_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_kdocs_type ON knowledge_documents(doc_type)")

            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS win_themes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    team_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    supporting_docs JSON,
                    metrics JSON,
                    times_used INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_win_themes_user ON win_themes(user_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_win_themes_cat ON win_themes(category)")

            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS rfp_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    team_id TEXT,
                    opportunity_id TEXT NOT NULL,
                    status TEXT DEFAULT 'draft',
                    version INTEGER DEFAULT 1,
                    selected_win_themes JSON,
                    selected_knowledge_docs JSON,
                    custom_instructions TEXT,
                    sections JSON,
                    compliance_score REAL,
                    compliance_issues JSON,
                    assigned_reviewers JSON,
                    review_comments JSON,
                    generated_at TIMESTAMP,
                    submitted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_rfp_responses_oppty ON rfp_responses(opportunity_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_rfp_responses_status ON rfp_responses(status)")

            # Add missing columns for existing deployments (SQLite-friendly)
            try:
                res_cols = await conn.exec_driver_sql("PRAGMA table_info('rfp_responses')")
                cols: Set[str] = {row._mapping["name"] for row in res_cols.fetchall()}
                if "review_comments" not in cols:
                    await conn.exec_driver_sql("ALTER TABLE rfp_responses ADD COLUMN review_comments JSON")
                if "assigned_reviewers" not in cols:
                    await conn.exec_driver_sql("ALTER TABLE rfp_responses ADD COLUMN assigned_reviewers JSON")
            except Exception:
                pass
    except Exception:
        return


async def ensure_extraction_cache_schema(engine) -> None:
    """Create extraction_cache table for LLM extraction caching."""
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS extraction_cache (
                    hash TEXT PRIMARY KEY,
                    result JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_extraction_cache_date ON extraction_cache(created_at)")
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


async def ensure_opportunity_extraction_schema(engine) -> None:
    """Ensure opportunities tables have json_blob for extracted metadata."""
    try:
        async with engine.begin() as conn:
            for table in ("opportunities", "opportunity"):
                try:
                    res = await conn.exec_driver_sql(f"PRAGMA table_info('{table}')")
                    cols: Set[str] = {row._mapping["name"] for row in res.fetchall()}
                    if not cols:
                        continue
                    if "json_blob" not in cols:
                        await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN json_blob JSON")
                except Exception:
                    continue
    except Exception:
        return


async def ensure_response_library_schema(engine) -> None:
    """Ensure response_library table exists for answer reuse."""
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='response_library'"
            )
            if not res.fetchone():
                await conn.exec_driver_sql(
                    """
                    CREATE TABLE response_library (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        team_id TEXT,
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        metadata JSON,
                        embedding TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                await conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_response_library_user ON response_library(user_id)"
                )
                await conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_response_library_team ON response_library(team_id)"
                )
    except Exception:
        return


async def ensure_ai_sessions_schema(engine) -> None:
    """Session persistence for AI Studio."""
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS ai_studio_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    team_id INTEGER,
                    opportunity_id TEXT,
                    name TEXT,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    sections_total INTEGER DEFAULT 0,
                    sections_completed INTEGER DEFAULT 0,
                    has_cover_letter INTEGER DEFAULT 0,
                    has_soq INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_ai_sessions_user ON ai_studio_sessions(user_id, last_accessed_at DESC)"
            )
    except Exception:
        return


async def ensure_ai_chat_schema(engine) -> None:
    """Create ai_chat_messages table for session-scoped Q&A."""
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS ai_chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_chat_session ON ai_chat_messages(session_id, created_at)"
            )
    except Exception:
        return
