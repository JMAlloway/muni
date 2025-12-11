from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import settings

if not settings.DB_URL:
    # Fail fast with a clear message instead of throwing from SQLAlchemy
    raise RuntimeError("DB_URL is not configured. Set it in environment or .env before starting the app.")

engine_kwargs = {"echo": False, "future": True}

# SQLite benefits from a single shared connection and longer busy timeout to avoid "database is locked".
if settings.DB_URL and settings.DB_URL.startswith("sqlite"):
    engine_kwargs.update(
        {
            "connect_args": {"timeout": 30, "check_same_thread": False},
            "poolclass": StaticPool,
        }
    )

engine = create_async_engine(settings.DB_URL, **engine_kwargs)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as s:
        yield s
