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
    first_name: Mapped[str | None] = mapped_column(String, default=None)
    last_name: Mapped[str | None] = mapped_column(String, default=None)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String, default="free")  # free, starter, professional, enterprise
    team_id: Mapped[str | None] = mapped_column(String, default=None, index=True)
    sms_phone: Mapped[str | None] = mapped_column(String, default=None)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    primary_interest: Mapped[str] = mapped_column(String, default="everything")
    onboarding_step: Mapped[str] = mapped_column(String, default="signup")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    first_tracked_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    stripe_customer_id: Mapped[str | None] = mapped_column(String, default=None)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, default=None)
    avatar_key: Mapped[str | None] = mapped_column(String, default=None)

class Opportunity(Base):
    __tablename__ = "opportunity"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    scope_of_work: Mapped[str | None] = mapped_column(Text, default="")
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


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, default="Team")
    owner_user_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str | None] = mapped_column(String, index=True, default=None)
    invited_email: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, default="member")  # owner, admin, member
    invited_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), default=None)


class BidNote(Base):
    __tablename__ = "bid_notes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String, index=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    author_user_id: Mapped[str] = mapped_column(String, index=True)
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)


class CompanyProfile(Base):
    __tablename__ = "company_profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), default=dt.datetime.utcnow)
