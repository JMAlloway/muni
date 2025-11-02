# app/models_core.py
from sqlalchemy import (
    Table, Column, MetaData, String, DateTime, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

metadata = MetaData()

opportunities = Table(
    "opportunities",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),

    # source info
    Column("source", String, nullable=False),
    Column("source_url", String, nullable=False, unique=True),

    # content
    Column("title", String, nullable=False),
    Column("summary", Text),          # short summary / dept
    Column("full_text", Text),        # long description / scope body
    Column("category", String),       # will show as "Type" in the UI
    Column("external_id", String),    # <--- NEW: RFQ / Solicitation #
    Column("keyword_tag", String),   # <-- NEW

    Column("agency_name", String),
    Column("location_geo", String),

    # dates
    Column("posted_date", DateTime),
    Column("due_date", DateTime),
    Column("prebid_date", DateTime),

    # extras
    Column("attachments", JSON),
    Column("status", String, default="open"),

    # tracking
    Column("hash_body", String),

    # bookkeeping
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
)
