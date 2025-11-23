from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import settings

if not settings.DB_URL:
    # Fail fast with a clear message instead of throwing from SQLAlchemy
    raise RuntimeError("DB_URL is not configured. Set it in environment or .env before starting the app.")

engine = create_async_engine(settings.DB_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as s:
        yield s
