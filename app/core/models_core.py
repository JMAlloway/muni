# app/models_core.py
from sqlalchemy import (
    Table, Column, MetaData, String, DateTime, Text, JSON, Float
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

metadata = MetaData()

opportunities = Table(
    "opportunities",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),

    # ------------------------------------------------------
    # Source info / identification
    # ------------------------------------------------------
    Column("source", String, nullable=False),
    Column("source_url", String, nullable=False, unique=True),

    # ------------------------------------------------------
    # Content and classification
    # ------------------------------------------------------
    Column("title", String, nullable=False),
    Column("summary", Text),
    Column("full_text", Text),
    Column("category", String),            # "construction", "it", etc.
    Column("ai_category", String),         # AI-normalized category (optional)
    Column("ai_confidence", Float),        # confidence in ai_category (0..1)
    Column("external_id", String),         # e.g., "2025-46-19"
    Column("keyword_tag", String),

    Column("agency_name", String),
    Column("location_geo", String),

    # ------------------------------------------------------
    # Dates (agency-posted)
    # ------------------------------------------------------
    Column("posted_date", DateTime),
    Column("due_date", DateTime),
    Column("prebid_date", DateTime),

    # ------------------------------------------------------
    # Attachments / misc
    # ------------------------------------------------------
    Column("attachments", JSON),
    Column("status", String, default="open"),

    # ------------------------------------------------------
    # Tracking / hashing
    # ------------------------------------------------------
    Column("hash_body", String),

    # ------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------
    Column("date_added", DateTime, default=datetime.utcnow, nullable=False),  # first-seen timestamp
    Column("last_seen", DateTime),  # 👈 NEW: last time the bid was seen in a scrape
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
)
