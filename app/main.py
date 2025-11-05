# app/main.py
import sys
import asyncio
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, PlainTextResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from app.routers import vendor_guides

# -------------------------------------------------------------------
# Windows event-loop quirk
# -------------------------------------------------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -------------------------------------------------------------------
# FastAPI app setup
# -------------------------------------------------------------------
app = FastAPI(title="Muni Alerts", version="0.3")

# -------------------------------------------------------------------
# Canonical host middleware (fixes cookie host mismatch)
# -------------------------------------------------------------------
CANONICAL_HOST = "127.0.0.1:8000"

class CanonicalHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if host and host != CANONICAL_HOST:
            target = f"{request.url.scheme}://{CANONICAL_HOST}{request.url.path}"
            if request.url.query:
                target += f"?{request.url.query}"
            return RedirectResponse(target, status_code=308)
        return await call_next(request)

app.add_middleware(CanonicalHostMiddleware)

# -------------------------------------------------------------------
# Static files
# -------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# -------------------------------------------------------------------
# Core imports (after app is defined)
# -------------------------------------------------------------------
from app.db import engine, AsyncSessionLocal
from app.models import Base
from app.models_core import metadata as core_metadata
from app.auth import create_admin_if_missing
from app.scheduler import start_scheduler
from app.session import get_current_user_email, SESSION_COOKIE_NAME
from app.auth_utils import require_login
from app.routers._layout import page_shell

# -------------------------------------------------------------------
# Log every request
# -------------------------------------------------------------------
@app.middleware("http")
async def log_every_request(request: Request, call_next):
    print(f"🛰  {request.method} {request.url.path}")
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    loc = response.headers.get("location")
    if loc:
        print(f"📤 {response.status_code} for {request.url.path} (route={route_path})  Location={loc}")
    else:
        print(f"📤 {response.status_code} for {request.url.path} (route={route_path})")
    return response

# -------------------------------------------------------------------
# HARD OVERRIDE: Real dashboard at /tracker/dashboard (wins precedence)
# -------------------------------------------------------------------
@app.get("/tracker/dashboard", include_in_schema=False)
async def dashboard_override(request: Request):
    user_email = get_current_user_email(request)

    # --- not logged in ---
    if not user_email:
        body = """
        <section class="card">
          <h2 class="section-heading">Sign in required</h2>
          <p class="subtext">Please log in to see your dashboard.</p>
          <a class="button-primary" href="/login?next=/tracker/dashboard">Sign in →</a>
        </section>
        """
        return HTMLResponse(page_shell(body, title="Muni Alerts – My Bids", user_email=None), status_code=200)

    # --- logged in ---
    sql = text("""
    WITH u AS (
      SELECT user_id, opportunity_id, COUNT(*) AS file_count, MAX(created_at) AS last_upload_at
      FROM user_uploads
      GROUP BY user_id, opportunity_id
    )
    SELECT
      t.opportunity_id,
      o.external_id,
      o.title,
      o.agency_name,
      o.due_date,
      COALESCE(o.ai_category, o.category) AS category,
      o.source_url,
      t.status,
      t.notes,
      t.created_at AS tracked_at,
      COALESCE(u.file_count, 0) AS file_count
    FROM user_bid_trackers t
    JOIN opportunities o ON o.id = t.opportunity_id
    LEFT JOIN u ON u.user_id = t.user_id AND u.opportunity_id = t.opportunity_id
    WHERE t.user_id = (SELECT id FROM users WHERE email = :email LIMIT 1)
    ORDER BY (o.due_date IS NULL) ASC, o.due_date ASC, t.created_at DESC
    """)

    async with engine.begin() as conn:
        # ✅ Correct call for TextClause
        res = await conn.execute(sql, {"email": user_email})
        items = [dict(row) for row in res.mappings().all()]

    items_json = json.dumps(items).replace("</", "<\\/")

    body = f"""
    <section class="card">
      <div class="head-row">
        <h2 class="section-heading">My Tracked Solicitations</h2>
        <div class="muted">Status, files, and step-by-step guidance.</div>
      </div>

      <div class="toolbar" id="dashboard-actions">
        <div class="filters">
          <select id="status-filter">
            <option value="">All statuses</option>
            <option value="prospecting">Prospecting</option>
            <option value="deciding">Deciding</option>
            <option value="drafting">Drafting</option>
            <option value="submitted">Submitted</option>
            <option value="won">Won</option>
            <option value="lost">Lost</option>
          </select>
          <select id="agency-filter">
            <option value="">All agencies</option>
            <option value="City of Columbus">City of Columbus</option>
            <option value="Central Ohio Transit Authority (COTA)">COTA</option>
          </select>
          <select id="sort-by">
            <option value="soonest">Soonest due</option>
            <option value="latest">Latest due</option>
            <option value="agency">Agency A–Z</option>
            <option value="title">Title A–Z</option>
          </select>
        </div>
      </div>

      <div id="tracked-grid" class="tracked-grid" data-items='{items_json}'></div>
    </section>

    <div id="guide-overlay"></div>
    <aside id="guide-drawer" aria-hidden="true">
      <header>
        <div>
          <h3 id="guide-title">How to bid</h3>
          <div id="guide-agency" class="muted"></div>
        </div>
        <button class="icon-btn" onclick="TrackerGuide.close()">×</button>
      </header>
      <div id="guide-content" class="guide-content">Loading…</div>
    </aside>

    <link rel="stylesheet" href="/static/dashboard.css">
    <link rel="stylesheet" href="/static/bid_tracker.css">
    <script src="/static/vendor.js"></script>
    <script src="/static/bid_tracker.js"></script>
    <script src="/static/tracker_dashboard.js"></script>
    """
    return HTMLResponse(page_shell(body, title="Muni Alerts – My Bids", user_email=user_email), status_code=200)

# -------------------------------------------------------------------
# Routers (existing)
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
    debug_cookies,
    dev_auth,
)
from app.routers.bid_tracker import router as tracker_router
from app.routers.uploads import router as uploads_router
from app.routers.zip import router as zip_router

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
app.include_router(vendor_guides.router) 

# -------------------------------------------------------------------
# Startup
# -------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(core_metadata.create_all)
    async with AsyncSessionLocal() as db:
        await create_admin_if_missing(db)
    start_scheduler()

# -------------------------------------------------------------------
# Global 401 → login redirect
# -------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def handle_http_exceptions(request: Request, exc: HTTPException):
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
# /whoami + /debug/session
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

@app.get("/debug/session")
async def debug_session(request: Request):
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    email = get_current_user_email(request)
    auth_result = await require_login(request)
    return {
        "cookie_present": bool(raw),
        "raw_cookie": raw,
        "parsed_email": email,
        "require_login_result": str(auth_result),
        "type": type(auth_result).__name__,
        "is_redirect": isinstance(auth_result, RedirectResponse)
    }
