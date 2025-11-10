# app/models_preferences.py

from sqlalchemy import (
    Table, Column, String, JSON, TIMESTAMP, text
)
from sqlalchemy.schema import MetaData
from sqlalchemy.sql import func

from app.core.db_core import engine

metadata = MetaData()

user_preferences = Table(
    "user_preferences",
    metadata,
    Column("user_email", String, primary_key=True),
    Column("agencies", JSON, nullable=True),
    Column("keywords", JSON, nullable=True),
    Column("frequency", String, nullable=True),  # daily | weekly | none
    Column("created_at", TIMESTAMP, server_default=func.now()),
    Column("updated_at", TIMESTAMP, server_default=func.now(), onupdate=func.now()),
)


# Stores per-user application variables (company info used in forms)
user_application_vars = Table(
    "user_application_vars",
    metadata,
    Column("user_email", String, primary_key=True),
    Column("data", JSON, nullable=True),
    Column("created_at", TIMESTAMP, server_default=func.now()),
    Column("updated_at", TIMESTAMP, server_default=func.now(), onupdate=func.now()),
)


async def create_user_preferences_table():
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
