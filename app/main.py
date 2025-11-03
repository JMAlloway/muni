import sys
import asyncio
from fastapi import FastAPI

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db import engine, AsyncSessionLocal
from app.models import Base
from app.auth import create_admin_if_missing
from app.scheduler import start_scheduler
from app.routers import marketing, opportunities, preferences, auth_web, admin
from app.routers import onboarding
from app.routers import columbus_detail
from app.routers import cota_detail
from app.routers import gahanna_detail
from app.routers import columbus_airports_detail
from app.routers import opportunity_web
from app.models_core import metadata as core_metadata
from app.routers import vendor_guides

from fastapi.staticfiles import StaticFiles


# if you also have users.router, include that too


app = FastAPI(title="Muni Alerts", version="0.1")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.models_core import metadata as core_metadata

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        # ORM tables
        await conn.run_sync(Base.metadata.create_all)
        # Core tables (opportunities)
        await conn.run_sync(core_metadata.create_all)
    ...

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        # ORM tables
        await conn.run_sync(Base.metadata.create_all)
        # Core tables (opportunities)
        await conn.run_sync(core_metadata.create_all)
    ...

@app.on_event("startup")
async def on_startup():
    # ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ensure ADMIN_EMAIL user exists / etc.
    async with AsyncSessionLocal() as db:
        await create_admin_if_missing(db)

    # kick off scraper + digests
    start_scheduler()


# Public product pages
app.include_router(marketing.router)        # "/"
app.include_router(opportunities.router)    # "/opportunities"
app.include_router(preferences.router)      # "/preferences"
app.include_router(onboarding.router)       # "/onboarding" 👈 new

# Auth / account
app.include_router(auth_web.router)         # "/signup", "/login", "/account", "/logout"

# Internal/admin tools
app.include_router(admin.router)            # "/admin/*"
app.include_router(columbus_detail.router)   # "/columbus_detail/{rfq_id}"
app.include_router(cota_detail.router)
app.include_router(gahanna_detail.router)
app.include_router(columbus_airports_detail.router)
app.include_router(opportunity_web.router)
app.include_router(vendor_guides.router)

