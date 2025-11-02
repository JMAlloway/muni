from sqlalchemy import text
from app.db_core import engine

async def ensure_user_preferences_table():
    create_sql = """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_email TEXT PRIMARY KEY,
        agencies TEXT,         -- JSON string list, e.g. ["City of Columbus","City of Gahanna"]
        keywords TEXT,         -- JSON string list, e.g. ["paving","hvac"]
        frequency TEXT,        -- 'daily' | 'weekly' | 'none'
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    async with engine.begin() as conn:
        await conn.execute(text(create_sql))
