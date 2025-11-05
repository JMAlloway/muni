# app/main.py

import sys
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.routers import debug_cookies
from app.routers import dev_auth

# -------------------------------------------------------------------
# Platform quirk fix (Windows)
# -------------------------------------------------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -------------------------------------------------------------------
# Canonical host middleware (fixes cookie host mismatch)
# -------------------------------------------------------------------
#CANONICAL_HOST = "127.0.0.1:8000"

#class CanonicalHostMiddleware(BaseHTTPMiddleware):
    #async def dispatch(self, request, call_next):
       # host = request.headers.get("host", "")
        #if host and host != CANONICAL_HOST:
            #target = f"{request.url.scheme}://{CANONICAL_HOST}{request.url.path}"
            #if request.url.query:
                #target += f"?{request.url.query}"
            #return RedirectResponse(target, status_code=308)
        #return await call_next(request)

# -------------------------------------------------------------------
# Database + startup helpers
# -------------------------------------------------------------------
from app.db import engine, AsyncSessionLocal
from app.models import Base
from app.models_core import metadata as core_metadata
from app.auth import create_admin_if_missing
from app.scheduler import start_scheduler
from app.session import get_current_user_email, SESSION_COOKIE_NAME

# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------
from app.routers import (
    marketing,
    opportunities,
    preferences,
    onboarding,
    auth_web,
    admin,
    columbus_detail,
    cota_detail,
    gahanna_detail,
    columbus_airports_detail,
    opportunity_web,
    vendor_guides,
    tracker_dashboard,
)
from app.routers.bid_tracker import router as tracker_router
from app.routers.uploads import router as uploads_router
from app.routers.zip import router as zip_router

# -------------------------------------------------------------------
# FastAPI setup
# -------------------------------------------------------------------
app = FastAPI(title="Muni Alerts", version="0.3")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Apply canonical host middleware (prevents localhost/127 mismatch)
#app.add_middleware(CanonicalHostMiddleware)

# -------------------------------------------------------------------
# Router includes (logical order)
# -------------------------------------------------------------------
app.include_router(marketing.router)
app.include_router(opportunities.router)
app.include_router(preferences.router)
app.include_router(onboarding.router)
app.include_router(auth_web.router)
app.include_router(tracker_router)
app.include_router(tracker_dashboard.router)
app.include_router(uploads_router)
app.include_router(zip_router)
app.include_router(vendor_guides.router)
app.include_router(opportunity_web.router)
app.include_router(columbus_detail.router)
app.include_router(cota_detail.router)
app.include_router(gahanna_detail.router)
app.include_router(columbus_airports_detail.router)
app.include_router(admin.router)
app.include_router(debug_cookies.router)
app.include_router(dev_auth.router)

# -------------------------------------------------------------------
# Startup event
# -------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(core_metadata.create_all)

    # Ensure admin exists
    async with AsyncSessionLocal() as db:
        await create_admin_if_missing(db)

    # Start scheduled jobs (ingestors, email digests, etc.)
    start_scheduler()

# -------------------------------------------------------------------
# Global error handling (convert 401 HTML → /login redirect)
# -------------------------------------------------------------------
# app/main.py (update the handler)

@app.exception_handler(HTTPException)
async def handle_http_exceptions(request: Request, exc: HTTPException):
    # Convert 401 → /login only for normal HTML pages, and never when already on /login
    if (
        exc.status_code == 401
        and "text/html" in request.headers.get("accept", "")
        and not request.url.path.startswith("/login")
    ):
        dest = request.url.path
        if request.url.query:
            dest += "?" + request.url.query
        return RedirectResponse(f"/login?next={dest}", status_code=303)
    raise exc

# -------------------------------------------------------------------
# Simple debug endpoint to verify cookie/session
# -------------------------------------------------------------------
@app.get("/whoami", response_class=PlainTextResponse)
def whoami(request: Request):
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    email = get_current_user_email(request)
    snippet = (raw[:32] + "...") if raw else "None"
    return (
        f"cookie_present={bool(raw)}\n"
        f"parsed_email={email}\n"
        f"cookie_value_snippet={snippet}\n"
        f"host={request.headers.get('host')}"
    )
