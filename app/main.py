# app/main.py
import sys
import asyncio
import json
import os
import re
import secrets
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, PlainTextResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from app.core.settings import settings

# -------------------------------------------------------------------
# Windows event-loop quirk
# -------------------------------------------------------------------
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -------------------------------------------------------------------
# FastAPI app setup
# -------------------------------------------------------------------
app = FastAPI(title="EasyRFP", version="0.3")

# -------------------------------------------------------------------
# Canonical host middleware (fixes cookie host mismatch)
# -------------------------------------------------------------------
CANONICAL_HOST = os.getenv("PUBLIC_APP_HOST")

if CANONICAL_HOST:
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
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# -------------------------------------------------------------------
# Core imports (after app is defined)
# -------------------------------------------------------------------
from app.core.db import engine, AsyncSessionLocal
from app.domain.models import Base
from app.core.models_core import metadata as core_metadata
from app.core.models_preferences import metadata as prefs_metadata
from app.auth import create_admin_if_missing, require_admin
from app.core.scheduler import start_scheduler
from app.auth.session import get_current_user_email, SESSION_COOKIE_NAME
from app.auth.auth_utils import require_login
from app.api._layout import page_shell
from app.core.db_migrations import (
    ensure_onboarding_schema,
    ensure_uploads_schema,
    ensure_team_schema,
    ensure_user_tier_column,
    ensure_billing_schema,
    ensure_company_profile_schema,
)
from app.api import dashboard_order as dashboard_order

# -------------------------------------------------------------------
# Log every request
# -------------------------------------------------------------------
@app.middleware("http")
async def log_every_request(request: Request, call_next):
    # ASCII-safe logs for Windows terminals
    try:
        print(f"[REQ] {request.method} {request.url.path}")
    except Exception:
        pass
    response = await call_next(request)
    try:
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        base = f"[RES] {response.status_code} for {request.url.path} (route={route_path})"
        loc = response.headers.get("location")
        if loc:
            print(base + f" Location={loc}")
        else:
            print(base)
    except Exception:
        pass
    return response

# -------------------------------------------------------------------
# Dev-only: disable caching for static assets to see live CSS/JS
# -------------------------------------------------------------------
@app.middleware("http")
async def disable_cache_for_static(request: Request, call_next):
    response = await call_next(request)
    try:
        env = (settings.ENV or "").lower()
        if env in {"local", "dev", "development"} and request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
    except Exception:
        pass
    return response

# -------------------------------------------------------------------
# CSRF protection (cookie 'csrftoken' + header 'X-CSRF-Token')
# -------------------------------------------------------------------
CSRF_COOKIE_NAME = "csrftoken"


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow Stripe webhook without CSRF
        if request.url.path == "/stripe/webhook":
            return await call_next(request)
        token = request.cookies.get(CSRF_COOKIE_NAME)
        # Only enforce on unsafe methods; allow auth endpoints without header
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.url.path in {"/login", "/signup"}:
                response = await call_next(request)
                if not token:
                    try:
                        t = secrets.token_urlsafe(32)
                        response.set_cookie(CSRF_COOKIE_NAME, t, httponly=False, samesite="lax")
                    except Exception:
                        pass
                return response
            ok = False
            hdr = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
            field = None

            def _norm(val):
                try:
                    v = (val or "").strip()
                    v = re.sub(r'^[\\"]+', "", v)
                    v = re.sub(r'[\\"]+$', "", v)
                    return v
                except Exception:
                    return val

            t_norm = _norm(token)
            h_norm = _norm(hdr)
            if t_norm and h_norm and h_norm == t_norm:
                ok = True
            else:
                try:
                    ctype = request.headers.get("content-type", "")
                    if "application/x-www-form-urlencoded" in ctype:
                        body = await request.body()
                        try:
                            request._body = body  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        data = parse_qs(body.decode(errors="ignore")) if body else {}
                        field_vals = data.get("csrf_token") or []
                        field = field_vals[0] if field_vals else None
                        f_norm = _norm(field)
                        if t_norm and f_norm and str(f_norm) == str(t_norm):
                            ok = True
                except Exception:
                    ok = False
            try:
                c8 = (t_norm or "")[:8]
                h8 = (h_norm or "")[:8]
                f8 = (_norm(field) or "")[:8]
                print(f"[CSRF] {request.method} {request.url.path} ok={ok} cookie={c8} hdr={h8} field={f8}")
            except Exception:
                pass
            if not ok:
                return PlainTextResponse("Forbidden (CSRF)", status_code=403)
        response = await call_next(request)
        try:
            if not token:
                t = secrets.token_urlsafe(32)
                response.set_cookie(CSRF_COOKIE_NAME, t, httponly=False, samesite="lax")
        except Exception:
            pass
        return response


app.add_middleware(CSRFMiddleware)

# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------
app.include_router(dashboard_order.router)

# -------------------------------------------------------------------
# HARD OVERRIDE: Real dashboard at /tracker/dashboard (wins precedence)
# -------------------------------------------------------------------
@app.get("/tracker/dashboard", include_in_schema=False)
async def dashboard_override(request: Request):
    from app.api.tracker_dashboard import tracker_dashboard as _dashboard

    return await _dashboard(request)


# -------------------------------------------------------------------
# Routers (existing)
# -------------------------------------------------------------------
from app.api import (
    marketing,
    opportunities,
    preferences,
    onboarding,
    auth_web,
    admin,
    billing,
    columbus_detail,
    documents,
    cota_detail,
    gahanna_detail,
    columbus_airports_detail,
    opportunity_web,
    calendar,
    unsubscribe,
    team,
    vendor_guides,
    tracker_dashboard,
    notifications,
    debug_cookies,
    dev_auth,
    welcome,
)
from app.api.bid_tracker import router as tracker_router
from app.api.uploads import router as uploads_router
from app.api.zip import router as zip_router

app.include_router(marketing.router)
app.include_router(opportunities.router)
app.include_router(preferences.router)
app.include_router(onboarding.router)
app.include_router(billing.router)
app.include_router(welcome.router)
app.include_router(auth_web.router)
app.include_router(tracker_router)
app.include_router(tracker_dashboard.router)
app.include_router(team.router)
app.include_router(uploads_router)
app.include_router(zip_router)
app.include_router(opportunity_web.router)
app.include_router(notifications.router)
app.include_router(calendar.router)
app.include_router(documents.router)
app.include_router(unsubscribe.router)
app.include_router(columbus_detail.router)
app.include_router(cota_detail.router)
app.include_router(gahanna_detail.router)
app.include_router(columbus_airports_detail.router)
app.include_router(admin.router)
app.include_router(debug_cookies.router)
app.include_router(dev_auth.router)
app.include_router(vendor_guides.router)

# -------------------------------------------------------------------
# Health check
# -------------------------------------------------------------------
@app.get("/health", include_in_schema=False)
async def health():
    return PlainTextResponse("ok")

# -------------------------------------------------------------------
# Startup
# -------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    # Only run DDL in environments that allow it (local/dev)
    if settings.RUN_DDL_ON_START:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(core_metadata.create_all)
            await conn.run_sync(prefs_metadata.create_all)
        async with AsyncSessionLocal() as db:
            await create_admin_if_missing(db)
        await ensure_uploads_schema(engine)
        await ensure_onboarding_schema(engine)
        await ensure_team_schema(engine)
        await ensure_user_tier_column(engine)
        await ensure_billing_schema(engine)
        await ensure_company_profile_schema(engine)
    if settings.START_SCHEDULER_WEB:
        start_scheduler()

# -------------------------------------------------------------------
# Global 401 -> login redirect
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
def whoami(request: Request, admin: bool = Depends(require_admin)):
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
async def debug_session(request: Request, admin: bool = Depends(require_admin)):
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    email = get_current_user_email(request)
    auth_result = await require_login(request)
    return {
        "cookie_present": bool(raw),
        "raw_cookie": raw,
        "parsed_email": email,
        "require_login_result": str(auth_result),
        "type": type(auth_result).__name__,
        "is_redirect": isinstance(auth_result, RedirectResponse),
    }
