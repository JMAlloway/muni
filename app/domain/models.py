from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Boolean, TIMESTAMP, JSON
import uuid, datetime as dt

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)

class Opportunity(Base):
    __tablename__ = "opportunity"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String, default="")
    agency_name: Mapped[str] = mapped_column(String, default="")
    location_geo: Mapped[str] = mapped_column(String, default="")
    posted_date: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    due_date: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    prebid_date: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    attachments: Mapped[dict] = mapped_column(JSON, default=list)
    hash_body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)

class Preference(Base):
    __tablename__ = "preference"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True)
    counties: Mapped[list[str]] = mapped_column(JSON, default=list)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    cadence: Mapped[str] = mapped_column(String, default="daily")
