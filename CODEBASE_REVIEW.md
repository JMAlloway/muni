# EasyRFP Codebase Review

**Date:** November 23, 2025
**Reviewer:** Claude Code
**Branch:** claude/codebase-review-heroku-0155yd5hFTsJoJBQyuJ5CaQS

---

## Executive Summary

EasyRFP is a well-architected FastAPI application for aggregating municipal RFP/RFQ opportunities. The codebase demonstrates solid async patterns and good separation of concerns. However, there are several areas that need attention before production deployment to Heroku.

---

## 1. Layout & Structure Improvements

### Current Strengths
- Clean separation: `app/api/`, `app/core/`, `app/domain/`, `app/ingest/`, `app/ai/`
- Server-side rendering with shared layout (`app/api/_layout.py`)
- Modular scraper architecture with per-municipality modules

### Issues Found

#### 1.1 Dead Code in `create_admin_if_missing()` (`app/auth/auth.py:16-26`)
```python
async def create_admin_if_missing(db: AsyncSession):
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return
        u = User(...)  # UNREACHABLE - this code never executes!
```
**Impact:** Admin user is never created on startup.

#### 1.2 Layout Tier Lookup Only Works with SQLite (`app/api/_layout.py:56-57`)
```python
if not db_url.startswith("sqlite"):
    return default  # PostgreSQL users always see "Free" tier!
```
**Impact:** On Heroku (PostgreSQL), tier badges won't display correctly.

#### 1.3 Duplicate Router Registration (`app/main.py`)
- `tracker_dashboard.router` is included twice (lines 208, 226)
- Dashboard override at line 183 conflicts with router

#### 1.4 Inconsistent Model Definitions
- `app/domain/models.py` uses SQLAlchemy ORM
- `app/core/models_core.py` uses SQLAlchemy Core (Table objects)
- Some queries reference columns that exist in one but not the other

### Recommendations
1. Fix the `create_admin_if_missing()` function - remove the early `return` or fix indentation
2. Rewrite `_get_user_tier_info()` to use async database calls that work with PostgreSQL
3. Clean up duplicate router registrations
4. Consolidate model definitions into a single approach

---

## 2. Style & CSS Improvements

### Current Strengths
- CSS custom properties (design tokens) in `:root`
- Dark mode support via `[data-theme="dark"]`
- Responsive sidebar with collapse functionality
- Good accessibility (ARIA attributes, focus states)

### Issues Found

#### 2.1 Mixed Color Schemes in Sidebar (`app/web/static/base.css`)
```css
.sidebar {
    background: linear-gradient(180deg,#e8f7ee 0%, #d9f0e5 100%); /* Light green */
    color: #0f1a17;
}
.sidebar .brand span {
    color:#e5e7eb; /* Light gray - invisible on light green! */
}
```

#### 2.2 No Theme Toggle UI
- Dark mode CSS exists but no user-facing toggle to enable it

#### 2.3 Missing Mobile Responsiveness
- No `@media` queries for small screens
- Sidebar doesn't hide on mobile
- Tables likely overflow on small viewports

#### 2.4 Inline Styles in Email Templates (`app/core/scheduler.py`)
- Email HTML uses hardcoded colors instead of consistent branding
- Consider using email template files or constants

### Recommendations
1. Fix sidebar brand text color (should be dark on light background)
2. Add mobile breakpoints (`@media (max-width: 768px)`)
3. Add theme toggle button to topbar
4. Create email template constants for consistent branding

---

## 3. Output & UX Improvements

### Current Strengths
- Real-time notification system with polling
- CSRF protection on forms
- Session-based auth with cookie fallback

### Issues Found

#### 3.1 Excessive Console Logging (191 `print()` calls across 35 files)
```python
print(f"[REQ] {request.method} {request.url.path}")
print(f"[CSRF] {request.method} {request.url.path} ok={ok}...")
print(f"[tier lookup] email={user_email} tier={effective_tier}...")
```
**Impact:** Log pollution, potential PII exposure, performance overhead on Heroku.

#### 3.2 No Error Pages
- Missing custom 404, 500 error templates
- Users see raw JSON or plain text on errors

#### 3.3 No Loading States
- Forms submit without visual feedback
- No skeleton loaders for async content

#### 3.4 Notification Polling Every 30 Seconds
```javascript
setInterval(fetchNotifs, 30000);
```
**Impact:** Continuous HTTP requests even when tab is inactive; wastes dyno time on Heroku.

### Recommendations
1. Replace `print()` with Python `logging` module
2. Add structured logging with log levels (DEBUG, INFO, WARN, ERROR)
3. Create custom error templates
4. Add loading spinners and skeleton states
5. Use Page Visibility API to pause polling when tab is hidden:
   ```javascript
   document.addEventListener('visibilitychange', () => {
     if (document.hidden) clearInterval(pollId);
     else pollId = setInterval(fetchNotifs, 30000);
   });
   ```

---

## 4. Features & Benefits Analysis

### Current Features
| Feature | Status | Tier Restriction |
|---------|--------|------------------|
| Opportunity feed | Working | None (24h delay for Free) |
| Bid tracking | Working | 3 bids (Free), unlimited (Paid) |
| Email digests | Working | Weekly (Free), Daily (Paid) |
| SMS alerts | Implemented | Paid tiers only |
| Team collaboration | Working | Professional+ |
| AI categorization | Working | All tiers |
| Stripe billing | Working | - |

### Missing/Incomplete Features

#### 4.1 No User Preferences Page
- `/account/preferences` link in nav but route may not exist
- Users can't change digest frequency in UI

#### 4.2 No Password Reset Flow
- No "forgot password" functionality
- No email verification on signup

#### 4.3 No Unsubscribe Link in Emails
```python
"To change preferences, update your account settings."  # Vague!
```
**Impact:** CAN-SPAM compliance issue

#### 4.4 Incomplete Onboarding
- `onboarding_step` and `onboarding_completed` fields exist
- Flow may not be fully implemented

#### 4.5 No Rate Limiting
- No protection against brute force login attempts
- No API rate limiting

### Recommended Features to Add
1. Password reset via email token
2. Email verification on signup
3. One-click unsubscribe links in digests
4. API rate limiting (use `slowapi` or similar)
5. User-facing preference management

---

## 5. Heroku Deployment Issues (CRITICAL)

### 5.1 Missing `runtime.txt`
**Issue:** No Python version specified; Heroku will use default (may differ from dev).

**Fix:** Create `runtime.txt`:
```
python-3.11.9
```

### 5.2 Missing Database Migration Command
**Issue:** `Procfile` doesn't run Alembic migrations on deploy.

**Current Procfile:**
```
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --log-level info
worker: python -m app.core.scheduler
```

**Recommended Procfile:**
```
release: alembic upgrade head
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --log-level info
worker: python -m app.core.scheduler
```

### 5.3 `RUN_DDL_ON_START=True` is Dangerous for Production
**Issue:** Running `create_all()` on startup can cause race conditions with multiple dynos.

**Fix in `app/core/settings.py`:**
```python
RUN_DDL_ON_START: bool = False  # Change default to False
```
Always use Alembic migrations in production.

### 5.4 Selenium/Chrome Won't Work on Heroku
**Issue:** Several scrapers use Selenium/Chrome:
- `city_columbus.py` (400+ lines)
- `columbus_airports.py`
- Others with `undetected-chromedriver`

**Impact:** Heroku dynos don't have Chrome installed. Scrapers will fail.

**Solutions:**
1. Add Chrome buildpack: `heroku buildpacks:add heroku/google-chrome`
2. Add Chromedriver buildpack: `heroku buildpacks:add heroku/chromedriver`
3. Set headless options properly:
   ```python
   options.add_argument('--headless=new')
   options.add_argument('--disable-dev-shm-usage')  # Critical for Heroku
   options.add_argument('--no-sandbox')
   ```
4. Or migrate to Playwright with browser download on build

### 5.5 Missing `psycopg` Binary
**Issue:** `requirements.txt` has `asyncpg` but some sync code may need `psycopg2-binary`.

**Fix:** Add to `requirements.txt`:
```
psycopg2-binary==2.9.9
```

### 5.6 Worker Dyno Configuration
**Issue:** APScheduler in worker dyno uses in-memory job store.

**Impact:** Job state lost on dyno restart; duplicate jobs if scaled to 2+ workers.

**Fix:** Use Heroku Redis for job store:
```python
from apscheduler.jobstores.redis import RedisJobStore
jobstores = {'default': RedisJobStore(host='...', port=6379)}
scheduler = AsyncIOScheduler(jobstores=jobstores, ...)
```

### 5.7 Static Files in Development Mode
**Issue:** FastAPI serves static files directly. Works but not optimal for production.

**Recommendation:** Use `whitenoise` middleware or serve from CDN/S3.

### 5.8 Session Cookie Security
**Current:**
```python
response.set_cookie(CSRF_COOKIE_NAME, t, httponly=False, samesite="lax")
```

**Missing for production:**
- `secure=True` for HTTPS-only cookies
- `domain` attribute for cross-subdomain issues

**Fix:**
```python
secure = settings.ENV == "production"
response.set_cookie(
    CSRF_COOKIE_NAME, t,
    httponly=False,
    samesite="lax",
    secure=secure,
)
```

### 5.9 Hardcoded Test Stripe Links
**Issue in `app/api/billing.py:130-134`:**
```python
payment_links = {
    "Starter": "https://buy.stripe.com/test_6oUfZj4DeaNkdzO3NXcV201",  # TEST!
    ...
}
```

**Fix:** Move to environment variables:
```python
payment_links = {
    "Starter": settings.STRIPE_LINK_STARTER or "...",
    ...
}
```

### 5.10 No Health Check Dependencies
**Issue:** `/health` returns "ok" without checking database connection.

**Improved health check:**
```python
@app.get("/health")
async def health():
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return PlainTextResponse(f"unhealthy: {e}", status_code=503)
```

---

## 6. Security Concerns

### 6.1 PII in Logs
```python
print(f"[tier lookup] email={user_email}...")
print(f"[digest:daily] sent to {email}")
```
**Fix:** Mask emails in logs: `user@d***.com`

### 6.2 No Input Validation on Some Endpoints
- SQL queries use parameterized queries (good)
- But some string interpolation in URLs could be XSS vectors

### 6.3 CSRF Token in URL Safe Form
```python
t = secrets.token_urlsafe(32)
```
Good practice, but ensure tokens are regenerated on login.

### 6.4 JWT Algorithm Should Be Explicit
```python
jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
```
Good - algorithm is specified, preventing algorithm confusion attacks.

---

## 7. Quick Wins Checklist

### Before Heroku Deploy
- [ ] Create `runtime.txt` with `python-3.11.9`
- [ ] Add `release: alembic upgrade head` to Procfile
- [ ] Set `RUN_DDL_ON_START=false` in Heroku config vars
- [ ] Add Chrome/Chromedriver buildpacks
- [ ] Add `psycopg2-binary` to requirements.txt
- [ ] Move Stripe payment links to environment variables
- [ ] Set `secure=True` on production cookies
- [ ] Fix `create_admin_if_missing()` dead code

### After Deploy
- [ ] Set up Heroku Redis for APScheduler job store
- [ ] Configure proper logging with Papertrail or similar
- [ ] Add Sentry for error tracking
- [ ] Set up database backups (Heroku PG automatic)
- [ ] Configure SSL/TLS (automatic on Heroku)

---

## 8. Environment Variables Checklist for Heroku

```bash
# Required
SECRET_KEY=<generate-secure-key>
DATABASE_URL=<automatic-from-postgres-addon>
ENV=production
PUBLIC_APP_HOST=www.easyrfp.ai
RUN_DDL_ON_START=false
START_SCHEDULER_WEB=false

# SMTP (Mailtrap or SendGrid)
SMTP_HOST=live.smtp.mailtrap.io
SMTP_PORT=587
SMTP_USERNAME=<key>
SMTP_PASSWORD=<secret>
SMTP_FROM=alerts@easyrfp.ai

# Stripe (use live keys!)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PROFESSIONAL=price_...
STRIPE_PRICE_ENTERPRISE=price_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Optional
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
AI_ENABLED=true
ai_provider=openai
openai_api_key=sk-...
```

---

## Summary

The EasyRFP codebase is well-structured and demonstrates good async Python practices. The main areas needing attention before production are:

1. **Critical:** Fix Selenium/Chrome for Heroku (add buildpacks)
2. **Critical:** Add `runtime.txt` and database migration to Procfile
3. **Critical:** Fix dead code in admin creation function
4. **High:** Fix tier lookup to work with PostgreSQL
5. **High:** Replace print statements with proper logging
6. **Medium:** Add mobile responsiveness
7. **Medium:** Implement password reset flow
8. **Low:** Consolidate model definitions

The application has a solid foundation for a SaaS product. With these fixes, it should deploy smoothly to Heroku.
