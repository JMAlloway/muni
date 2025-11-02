# app/models_preferences.py

from sqlalchemy import (
    Table, Column, String, JSON, TIMESTAMP, text
)
from app.db_core import engine
from sqlalchemy.sql import func
from sqlalchemy.schema import MetaData

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


async def create_user_preferences_table():
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
