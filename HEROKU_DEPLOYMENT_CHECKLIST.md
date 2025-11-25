# Heroku Deployment Checklist for EasyRFP

**Last Updated**: 2025-11-25
**Target Branch**: `claude/codebase-review-heroku-0155yd5hFTsJoJBQyuJ5CaQS`

---

## ✅ Already Completed (Ready for Deployment)

These critical fixes have been applied and committed:

- [x] **Created `runtime.txt`** - Specifies Python 3.11.9 for Heroku
- [x] **Updated `Procfile`** - Added `release: alembic upgrade head` for database migrations
- [x] **Fixed admin creation bug** - `app/auth/auth.py` now properly creates admin users
- [x] **PostgreSQL tier lookup** - `app/api/_layout.py` now supports PostgreSQL for tier badges
- [x] **Added `psycopg2-binary`** - PostgreSQL sync driver in requirements.txt
- [x] **Changed `RUN_DDL_ON_START`** - Set to `False` (safer for production)
- [x] **Created design system** - tokens.css, components.css, toast.js, DESIGN_SYSTEM.md
- [x] **Comprehensive codebase review** - CODEBASE_REVIEW.md with all findings

---

## 🔴 CRITICAL - Must Fix Before Deploy

### 1. Configure Heroku Buildpacks for Selenium Scrapers

**Issue**: Scrapers for Plymouth, Manchester, Chicopee use Selenium with Chrome
**Location**: `app/scrapers/ma_*.py`
**Impact**: Scrapers will fail without Chrome/ChromeDriver on Heroku

**Fix Steps**:
```bash
# Add buildpacks in this order:
heroku buildpacks:add --index 1 heroku/python
heroku buildpacks:add --index 2 https://github.com/heroku/heroku-buildpack-google-chrome
heroku buildpacks:add --index 3 https://github.com/heroku/heroku-buildpack-chromedriver
```

**Code Changes Required**:
Update `app/scrapers/ma_*.py` to use headless Chrome:
```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def get_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = "/app/.apt/usr/bin/google-chrome"  # Heroku path
    return webdriver.Chrome(options=chrome_options)
```

**Alternative**: Consider migrating to Playwright (already in requirements.txt):
- Playwright is more stable on Heroku
- Better async support
- Easier headless configuration

---

### 2. Move Stripe Test Links to Environment Variables

**Issue**: Hardcoded test payment links in `app/web/routes.py`
**Location**: Lines 142-145
**Impact**: Test mode links will be exposed in production

**Current Code** (lines 142-145):
```python
payment_link_map = {
    "Professional": "https://buy.stripe.com/test_6oE5oe5h99XE0gM8wx",
    "Team": "https://buy.stripe.com/test_cN2eYUgVP6Lsbbo7st"
}
```

**Fix**:
1. Add to `.env`:
```bash
STRIPE_PROFESSIONAL_LINK=https://buy.stripe.com/your_live_professional_link
STRIPE_TEAM_LINK=https://buy.stripe.com/your_live_team_link
```

2. Update `app/core/settings.py`:
```python
STRIPE_PROFESSIONAL_LINK: str = Field(default="")
STRIPE_TEAM_LINK: str = Field(default="")
```

3. Update `app/web/routes.py`:
```python
payment_link_map = {
    "Professional": settings.STRIPE_PROFESSIONAL_LINK,
    "Team": settings.STRIPE_TEAM_LINK
}
```

---

### 3. Add Unsubscribe Links to Email Digests

**Issue**: CAN-SPAM compliance violation - no unsubscribe mechanism
**Location**: `app/services/digest.py` lines 67-92
**Impact**: Legal violations, potential fines, email deliverability issues

**Required Changes**:

1. Add email preferences route in `app/web/routes.py`:
```python
@router.get("/preferences/email/{token}")
async def email_preferences(token: str, db: AsyncSession = Depends(get_async_db)):
    # Validate token, show unsubscribe form
    pass

@router.post("/preferences/unsubscribe")
async def unsubscribe_email(email: str, db: AsyncSession = Depends(get_async_db)):
    # Set user.digest_enabled = False
    pass
```

2. Update digest email template (lines 80-91):
```python
<p style="font-size:12px;color:#64748b;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:12px;">
    You're receiving this because you opted in to email digests.<br>
    <a href="{base_url}/preferences/email/{unsubscribe_token}">Unsubscribe</a> |
    <a href="{base_url}/preferences">Manage Preferences</a>
</p>
```

---

### 4. Configure SESSION_COOKIE_SECURE for Production

**Issue**: Session cookies sent over HTTP in production
**Location**: `app/auth/session.py` line 15
**Impact**: Session hijacking vulnerability over non-HTTPS connections

**Current Code** (line 15):
```python
SESSION_COOKIE_SECURE = False  # Set True in production w/ HTTPS
```

**Fix**:
1. Update `app/core/settings.py`:
```python
SESSION_COOKIE_SECURE: bool = Field(default=True)
```

2. For local development, set in `.env.local`:
```bash
SESSION_COOKIE_SECURE=false
```

3. Heroku config (automatic):
```bash
heroku config:set SESSION_COOKIE_SECURE=true
```

---

### 5. Set Up Required Heroku Add-ons

**Required Add-ons**:

1. **PostgreSQL Database**:
```bash
heroku addons:create heroku-postgresql:mini
# This sets DATABASE_URL automatically
```

2. **Redis for Session Storage** (recommended):
```bash
heroku addons:create heroku-redis:mini
# This sets REDIS_URL automatically
```

3. **Papertrail for Logging** (recommended):
```bash
heroku addons:create papertrail:choklad
```

4. **Scheduler for Background Jobs**:
```bash
heroku addons:create scheduler:standard
# Then configure jobs in Heroku dashboard
```

---

### 6. Configure All Environment Variables

**Critical Environment Variables** (must be set on Heroku):

```bash
# Database (auto-set by heroku-postgresql addon)
DATABASE_URL=postgresql://...

# Security
SECRET_KEY=<generate-with-openssl-rand-hex-32>
SESSION_COOKIE_SECURE=true

# Admin Account
ADMIN_EMAIL=admin@easyrfp.com
ADMIN_PASSWORD=<strong-password>

# Stripe (LIVE mode keys)
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PROFESSIONAL_LINK=https://buy.stripe.com/...
STRIPE_TEAM_LINK=https://buy.stripe.com/...

# Email (if using SendGrid/Mailgun)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.xxxxx
FROM_EMAIL=noreply@easyrfp.com

# AI/LLM (if using OpenAI)
OPENAI_API_KEY=sk-...

# Application
APP_ENV=production
BASE_URL=https://easyrfp.herokuapp.com
RUN_DDL_ON_START=false
```

**Command to Set Variables**:
```bash
heroku config:set SECRET_KEY=$(openssl rand -hex 32)
heroku config:set SESSION_COOKIE_SECURE=true
heroku config:set ADMIN_EMAIL=admin@easyrfp.com
heroku config:set ADMIN_PASSWORD="YourStrongPassword"
heroku config:set STRIPE_API_KEY=sk_live_...
# ... etc
```

---

## 🟠 HIGH PRIORITY - Strongly Recommended Before Deploy

### 7. Replace print() Statements with Logging

**Issue**: 191 print() statements throughout codebase
**Impact**: Lost logs in production, no log levels, hard to debug

**Files with Most print() Statements**:
- `app/scrapers/ma_*.py` - 8-10 per scraper
- `app/api/opportunities.py` - 10+ statements
- `app/services/*.py` - Various files

**Fix**:
```python
# Instead of:
print("Scraping opportunities...")

# Use:
import logging
logger = logging.getLogger(__name__)
logger.info("Scraping opportunities...")
```

**Configure logging in `app/main.py`**:
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

---

### 8. Add Health Check Endpoint

**Issue**: No endpoint for Heroku/monitoring to verify app health
**Impact**: Can't monitor uptime, hard to debug deployment issues

**Add to `app/web/routes.py`**:
```python
@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """Health check endpoint for monitoring."""
    try:
        # Test database connection
        await db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )
```

---

### 9. Configure Gunicorn Workers Properly

**Issue**: Default Gunicorn config may not be optimal for Heroku dynos
**Location**: `Procfile`

**Current**:
```
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --log-level info
```

**Recommended for Heroku Standard-1X/2X**:
```
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --timeout 120 --log-level info --access-logfile - --error-logfile -
```

Workers formula: `(2 x CPU cores) + 1`
- Standard-1X: 1 core → 2 workers
- Standard-2X: 2 cores → 4 workers

---

### 10. Test Database Migrations Locally

**Action**: Verify Alembic migrations work before deploying

```bash
# Test with PostgreSQL locally (not SQLite)
export DATABASE_URL="postgresql://localhost/easyrfp_test"

# Run migrations
alembic upgrade head

# Verify all tables created
psql easyrfp_test -c "\dt"

# Test downgrade (rollback)
alembic downgrade -1
alembic upgrade head
```

---

## 🟡 MEDIUM PRIORITY - Should Do Soon After Deploy

### 11. Add Error Monitoring (Sentry)

**Why**: Track production errors, get alerts for crashes

```bash
pip install sentry-sdk[fastapi]
```

Add to `app/main.py`:
```python
import sentry_sdk

if settings.APP_ENV == "production":
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,
    )
```

---

### 12. Replace Inline Styles with CSS Classes

**Issue**: Inline styles in Python route files
**Files**: `app/web/routes.py`, `app/api/*.py`
**Impact**: Inconsistent UI, hard to maintain

**Example from `app/web/routes.py` line 283**:
```python
# Before:
"style='background:#2563eb;color:#fff;padding:6px 10px;border-radius:6px;'"

# After:
"class='btn-primary btn-sm'"
```

**Action**: Search for `style=` in all Python files and replace with CSS classes from design system.

---

### 13. Add Mobile Responsiveness

**Issue**: No mobile-specific styles
**Location**: CSS files lack responsive breakpoints

**Add to `app/web/static/css/layout.css`**:
```css
@media (max-width: 768px) {
    .sidebar { display: none; }
    .main-content { margin-left: 0; }
    .topbar { padding-left: 16px; }
}
```

---

### 14. Add Rate Limiting

**Why**: Prevent abuse, protect scrapers and API

```bash
pip install slowapi
```

Add to `app/main.py`:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Apply to routes:
```python
@router.post("/api/track-bid")
@limiter.limit("10/minute")
async def track_bid(request: Request, ...):
    pass
```

---

### 15. Set Up Background Worker on Heroku

**Action**: Configure APScheduler to run on separate dyno

Update `Procfile`:
```
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --workers 2 --log-level info
release: alembic upgrade head
worker: python -m app.core.scheduler
```

**Important**: The worker dyno runs the scheduler separately from the web dyno.

Enable worker dyno:
```bash
heroku ps:scale worker=1
```

**Cost**: Worker dyno costs same as web dyno (~$7/month for Eco)

---

## 🟢 LOW PRIORITY - Nice to Have

### 16. Add API Documentation with Swagger

**Status**: FastAPI auto-generates docs at `/docs`
**Action**: Make sure it's enabled in production

In `app/main.py`:
```python
app = FastAPI(
    title="EasyRFP API",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None
)
```

Or keep it enabled for admin users only.

---

### 17. Add User Analytics

**Options**:
- Google Analytics
- Mixpanel
- Plausible (privacy-friendly)

Add tracking script to `app/api/_layout.py` base template.

---

### 18. Implement Dark Mode Toggle

**Status**: Dark mode CSS already created in tokens.css
**Action**: Add toggle button in UI

Add to `app/api/_layout.py` topbar:
```html
<button onclick="toggleDarkMode()" class="btn-icon">
    🌙
</button>

<script>
function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

// Load saved preference
const saved = localStorage.getItem('theme');
if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
}
</script>
```

---

## 📋 Pre-Deployment Testing Checklist

Run these tests before deploying:

### Local Testing
- [ ] Run all scrapers locally: `python -m app.core.scheduler` (manual test)
- [ ] Test Stripe checkout flow with test mode
- [ ] Verify email digests send correctly
- [ ] Test team member invitations
- [ ] Check all pages load without errors
- [ ] Test mobile responsiveness in browser dev tools

### Staging Deployment (Recommended)
```bash
# Create staging app
heroku create easyrfp-staging

# Deploy to staging first
git push heroku-staging claude/codebase-review-heroku-0155yd5hFTsJoJBQyuJ5CaQS:main

# Test on staging
# If successful, deploy to production
```

### Database Testing
- [ ] Test migrations: `alembic upgrade head`
- [ ] Verify all tables created
- [ ] Test admin user creation
- [ ] Test user registration flow
- [ ] Verify tier badges display correctly

---

## 🚀 Deployment Commands

### First-Time Deployment

```bash
# 1. Create Heroku app
heroku create easyrfp

# 2. Add buildpacks
heroku buildpacks:add --index 1 heroku/python
heroku buildpacks:add --index 2 https://github.com/heroku/heroku-buildpack-google-chrome
heroku buildpacks:add --index 3 https://github.com/heroku/heroku-buildpack-chromedriver

# 3. Add PostgreSQL addon
heroku addons:create heroku-postgresql:mini

# 4. Set environment variables
heroku config:set SECRET_KEY=$(openssl rand -hex 32)
heroku config:set SESSION_COOKIE_SECURE=true
heroku config:set ADMIN_EMAIL=admin@easyrfp.com
heroku config:set ADMIN_PASSWORD="YourStrongPassword"
heroku config:set STRIPE_API_KEY=sk_live_...
heroku config:set APP_ENV=production
heroku config:set BASE_URL=https://easyrfp.herokuapp.com
heroku config:set RUN_DDL_ON_START=false

# 5. Deploy
git push heroku claude/codebase-review-heroku-0155yd5hFTsJoJBQyuJ5CaQS:main

# 6. Scale dynos
heroku ps:scale web=1 worker=1

# 7. Check logs
heroku logs --tail
```

### Subsequent Deployments

```bash
# Push updates
git push heroku claude/codebase-review-heroku-0155yd5hFTsJoJBQyuJ5CaQS:main

# Monitor deployment
heroku logs --tail

# Check dyno status
heroku ps

# Run migrations manually (if needed)
heroku run alembic upgrade head
```

---

## ✅ Post-Deployment Verification

After deploying, verify these items:

### Immediate Checks (within 5 minutes)
- [ ] App loads: `https://easyrfp.herokuapp.com`
- [ ] Health check passes: `https://easyrfp.herokuapp.com/health`
- [ ] Database connected (check health endpoint)
- [ ] Admin login works
- [ ] Static files load (CSS, JS)
- [ ] No errors in logs: `heroku logs --tail`

### Within 1 Hour
- [ ] Register new user account
- [ ] Set user preferences
- [ ] Search for opportunities
- [ ] Track a bid
- [ ] Verify tier badge displays
- [ ] Check email notifications work

### Within 24 Hours
- [ ] Verify scrapers run successfully
- [ ] Check digest emails sent
- [ ] Monitor error rates in logs
- [ ] Test Stripe subscription flow (use test mode)
- [ ] Verify team invitations work

### Within 1 Week
- [ ] Monitor database size: `heroku pg:info`
- [ ] Check dyno metrics: `heroku ps`
- [ ] Review logs for errors: `heroku logs -n 1000`
- [ ] Test all municipality scrapers
- [ ] Monitor memory usage

---

## 📊 Monitoring & Maintenance

### Daily
- Check `heroku logs --tail` for errors
- Monitor scraper success rates
- Review user registrations

### Weekly
- Database backup: `heroku pg:backups:capture`
- Review dyno metrics
- Check email deliverability
- Update dependencies: `pip list --outdated`

### Monthly
- Review Heroku costs
- Analyze user growth
- Check scraper accuracy
- Update Chrome/ChromeDriver if needed

---

## 🆘 Troubleshooting Common Issues

### Issue: Scrapers Fail After Deploy
**Solution**: Check buildpacks are installed, verify Chrome path in code

### Issue: Database Connection Errors
**Solution**: Verify `DATABASE_URL` is set, check connection pool settings

### Issue: Session Cookie Not Working
**Solution**: Ensure `SESSION_COOKIE_SECURE=true` and app uses HTTPS

### Issue: Static Files 404
**Solution**: Check `/static` route in FastAPI, verify file paths

### Issue: Slow Response Times
**Solution**: Scale up dynos or add more workers

---

## 📞 Support Resources

- **Heroku Docs**: https://devcenter.heroku.com/
- **FastAPI Deployment**: https://fastapi.tiangolo.com/deployment/
- **Stripe Docs**: https://stripe.com/docs
- **APScheduler**: https://apscheduler.readthedocs.io/

---

## Summary

**Ready to Deploy**: ✅ Core infrastructure fixes completed
**Critical Items**: 🔴 6 items must be addressed before going live
**High Priority**: 🟠 4 items strongly recommended
**Medium/Low Priority**: 🟡🟢 Can be addressed post-deployment

**Estimated Time to Production-Ready**: 4-6 hours (if addressing all critical items)

Good luck with your deployment! 🚀
