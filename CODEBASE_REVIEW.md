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

---

# Part 2: Feature Improvements

## 9. Onboarding Flow Enhancements

### Current State
- Multi-step form: Industry → Agency → Email frequency → Keywords
- Interest profiles in `app/onboarding/interests.py`
- Milestone tracking via `user_onboarding_events` table

### Issues Found
| Issue | Location | Impact |
|-------|----------|--------|
| Industry selection NOT persisted | `app/api/onboarding.py:461` | User selections are lost |
| No email verification | - | Fake emails can subscribe |
| Hardcoded industries (only 8) | `app/api/onboarding.py:31-38` | Limited customization |
| No abandonment tracking | - | Can't recover incomplete signups |

### Recommended Improvements

**9.1 Persist Industry Selection**
```python
# Create user_industries table
# Store selected industries from onboarding step 1
# Use for recommendation engine
```

**9.2 Add Email Verification**
- Send confirmation email with token on signup
- Block digest emails until verified
- Add `email_verified` column to users table

**9.3 Onboarding Progress Bar**
- Show "Step 2 of 4" visual indicator
- Track estimated completion time
- Enable back/forward navigation

**9.4 Abandonment Recovery**
- Email users who started but didn't complete after 3 days
- Offer simplified "quick setup" alternative
- Track abandonment reasons for optimization

---

## 10. User Preferences Enhancements

### Current State
- Preferences split across `users` and `user_preferences` tables
- Agency filtering via checkboxes (20 agencies)
- SMS opt-in with phone verification
- Application variables form for company details

### Issues Found
- No saved search functionality
- No budget/contract value filtering
- No geographic/location filtering
- No capability-based filtering (match certs to requirements)

### Recommended Improvements

**10.1 Saved Searches**
```sql
CREATE TABLE saved_searches (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    name VARCHAR(100),
    filter_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```
- Quick-apply buttons in opportunities UI
- Share saved searches with team

**10.2 Budget Range Filter**
- Extract estimated contract value from opportunity text using AI
- Store in `opportunities.estimated_budget_min/max`
- Add slider filter: "$0-$50K", "$50K-$250K", "$250K-$1M", "$1M+"

**10.3 Capability Matching**
- Cross-reference user's certifications with opportunity requirements
- Show "Qualifications Match" badge (0-100%)
- Surface highly-matched opportunities first in feed

**10.4 Preference Analytics**
- Track which filters users apply most
- Suggest optimized defaults based on behavior
- Show "Users like you also filter by..." suggestions

---

## 11. Notification System Enhancements

### Current State
- In-app notifications only
- Team invite notifications work
- 30-second polling in browser

### Issues Found
- No email/SMS/push notification delivery
- No notification preferences (users can't control what they receive)
- No notification batching/digest
- Polling wastes resources when tab is inactive

### Recommended Improvements

**11.1 Multi-Channel Delivery**
| Channel | Implementation | Priority |
|---------|---------------|----------|
| Email | SMTP via existing emailer | High |
| SMS | Twilio (already integrated) | Medium |
| Push | OneSignal or Firebase | Low |

**11.2 Notification Preference Center**
```python
# Add to /api/preferences/notifications
notification_preferences = {
    "team_invite": {"in_app": True, "email": True, "sms": False},
    "bid_due_soon": {"in_app": True, "email": True, "sms": True},
    "new_opportunities": {"in_app": False, "email": True, "sms": False},
    "team_note_mention": {"in_app": True, "email": True, "sms": False},
}
```

**11.3 Smart Polling**
```javascript
// Use Page Visibility API to pause polling when tab is hidden
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        clearInterval(pollInterval);
    } else {
        pollInterval = setInterval(fetchNotifs, 30000);
        fetchNotifs(); // Immediate refresh on return
    }
});
```

**11.4 Notification Threading**
- Group related notifications (e.g., all mentions from same bid)
- Show collapsed threads in drawer
- Add `parent_notification_id` column

---

## 12. Team Collaboration Enhancements

### Current State
- Basic team creation and member invitations
- Shared bid tracking across team
- Notes with @mentions on tracked bids
- Seat limits: 4 (Professional), 50 (Enterprise)

### Issues Found
- Only owner/member roles (no granular permissions)
- No audit logging for compliance
- No team-level settings
- No activity tracking or analytics
- Tier enforcement commented out (`app/api/team.py:35-36`)

### Recommended Improvements

**12.1 Role-Based Access Control**
| Role | Permissions |
|------|-------------|
| Owner | Full access, billing, delete team |
| Manager | Invite/remove members, edit settings |
| Member | Track bids, add notes, view all |
| Viewer | Read-only access to tracked bids |

**12.2 Team Audit Log**
```sql
CREATE TABLE team_audit_log (
    id UUID PRIMARY KEY,
    team_id UUID REFERENCES teams(id),
    actor_user_id UUID REFERENCES users(id),
    action VARCHAR(50),  -- 'member_invited', 'note_created', 'bid_tracked'
    resource_type VARCHAR(50),
    resource_id UUID,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**12.3 Team Activity Dashboard**
- Recent actions feed: "John tracked RFQ-123", "Jane added note"
- Activity heatmap (by day/hour)
- Member contribution metrics
- Filter by member or date range

**12.4 Team Notifications**
- Notify members when @mentioned in notes
- Alert team when new bids are tracked
- Weekly team activity summary email

---

## 13. Bid Tracking Enhancements

### Current State
- Track/untrack opportunities
- Status and notes per tracked bid
- Team visibility for shared tracking
- Basic dashboard view

### Issues Found
- No predefined status workflow
- No due date alerts/reminders
- No outcome tracking (won/lost)
- No assignment to team members
- No calendar integration

### Recommended Improvements

**13.1 Status Workflow**
```
watching → responding → submitted → won/lost/passed
                     ↘ passed
```
- Visual progress indicator
- Automatic status suggestions based on due date

**13.2 Due Date Alerts**
| Alert | Timing | Channel |
|-------|--------|---------|
| Early warning | 7 days before | Email |
| Approaching | 3 days before | Email + In-app |
| Urgent | 1 day before | Email + SMS |
| Expired | Day after due | In-app only |

**13.3 Outcome Tracking**
```sql
ALTER TABLE user_bid_trackers ADD COLUMN
    outcome VARCHAR(20),  -- 'won', 'lost', 'passed', 'submitted'
    outcome_date TIMESTAMP,
    award_value DECIMAL(15,2),
    outcome_notes TEXT;
```
- Win rate analytics by category/agency
- Revenue forecasting from submitted bids

**13.4 Bid Assignment**
- Add `assigned_to_user_id` column
- Assignment notification
- Filter dashboard by "My assignments"
- Reassignment history tracking

**13.5 Calendar Integration**
- Generate iCal feed URL: `/api/calendar/ical/{user_token}`
- Include: tracked bid due dates, prebid meetings
- Works with Google Calendar, Outlook, Apple Calendar

---

## 14. Opportunities Feed Enhancements

### Current State
- Agency, keyword, due date filtering
- Sort by due date or alphabetically
- Pagination (25 items/page)
- Tag/specialty filtering

### Issues Found
- Basic LIKE search (no full-text search)
- No typo tolerance
- No saved/bookmarked opportunities
- No recommendation engine
- No search analytics

### Recommended Improvements

**14.1 Full-Text Search**
```sql
-- PostgreSQL
ALTER TABLE opportunities ADD COLUMN search_vector tsvector;
CREATE INDEX opportunities_search_idx ON opportunities USING gin(search_vector);

-- Update trigger
UPDATE opportunities SET search_vector =
    to_tsvector('english', coalesce(title,'') || ' ' ||
                coalesce(summary,'') || ' ' ||
                coalesce(full_text,''));
```

**14.2 Search Autocomplete**
- Endpoint: `GET /api/search/suggest?q=constr`
- Returns: matching agencies, keywords, recent searches
- Typo tolerance using Levenshtein distance

**14.3 Bookmarking System**
```sql
CREATE TABLE user_bookmarks (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    opportunity_id UUID REFERENCES opportunities(id),
    folder VARCHAR(100) DEFAULT 'default',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, opportunity_id)
);
```

**14.4 Recommendation Engine**
- Collaborative filtering: "Users who tracked X also tracked Y"
- Content-based: similar opportunities to recently tracked
- Endpoint: `GET /api/opportunities/recommended?limit=10`
- Show "Recommended for you" section in feed

**14.5 Opportunity Comparison**
- Multi-select up to 3 opportunities
- Side-by-side comparison view
- Export comparison to PDF
- Share comparison with team

---

## 15. AI Classification Enhancements

### Current State
- Keyword-based category classification
- Deterministic specialty tagging
- Optional LLM fallback for weak matches
- AI summary generation

### Issues Found
- No feedback loop for misclassifications
- Single category per opportunity (no multi-label)
- No entity extraction (contacts, locations)
- No classification audit trail

### Recommended Improvements

**15.1 Classification Feedback**
```sql
CREATE TABLE classification_feedback (
    id UUID PRIMARY KEY,
    opportunity_id UUID REFERENCES opportunities(id),
    user_id UUID REFERENCES users(id),
    field VARCHAR(50),  -- 'category', 'tags', 'summary'
    original_value TEXT,
    suggested_value TEXT,
    feedback_type VARCHAR(20),  -- 'incorrect', 'missing', 'spam'
    created_at TIMESTAMP DEFAULT NOW()
);
```
- "Is this correct?" button on opportunity view
- Use feedback to retrain classifiers
- Track classification accuracy over time

**15.2 Multi-Label Classification**
- Store multiple categories: `ai_categories: ["Construction", "IT"]`
- Show category badges (e.g., "Construction | Professional Services")
- Filter supports OR matching on categories

**15.3 Entity Extraction**
- Extract from opportunity text:
  - Contact emails/phones
  - Project location/address
  - Key dates mentioned
  - Dollar amounts/budgets
- Store in `opportunity_entities` table
- Enable geographic filtering

**15.4 Change Detection**
- Hash opportunity content
- Detect significant changes on re-scrape
- Generate "Updated" notifications for tracked bids
- Show change diff in UI

---

## 16. Email Digest Enhancements

### Current State
- Daily and weekly digest options
- Grouped by agency
- AI summaries and tags included
- SMS nudge for premium tiers

### Issues Found
- No unsubscribe link (CAN-SPAM compliance issue!)
- No engagement tracking (opens/clicks)
- No digest customization
- No digest preview capability

### Recommended Improvements

**16.1 Unsubscribe Link (CRITICAL)**
```python
# Add to every digest email footer
unsubscribe_token = generate_secure_token(user_id)
unsubscribe_url = f"{APP_BASE_URL}/email/unsubscribe/{unsubscribe_token}"

footer = f"""
<p style="font-size:11px;color:#888;">
    <a href="{unsubscribe_url}">Unsubscribe</a> |
    <a href="{APP_BASE_URL}/preferences">Manage preferences</a>
</p>
"""
```

**16.2 Engagement Tracking**
```sql
CREATE TABLE email_events (
    id UUID PRIMARY KEY,
    user_id UUID,
    digest_id UUID,
    event_type VARCHAR(20),  -- 'sent', 'opened', 'clicked'
    opportunity_id UUID,  -- for click events
    timestamp TIMESTAMP DEFAULT NOW()
);
```
- Pixel tracking for opens
- Link tracking for clicks
- Dashboard: open rate, CTR, popular opportunities

**16.3 Digest Customization**
```python
# User preferences
digest_settings = {
    "format": "detailed",  # compact, detailed, visual
    "max_items": 20,
    "include_summary": True,
    "include_tags": True,
    "sort_by": "relevance",  # due_date, relevance, agency
    "agencies_first": ["City of Columbus", "COTA"],
}
```

**16.4 Digest Preview**
- Endpoint: `GET /api/digest/preview`
- Show sample digest before subscribing
- "Send test to myself" button
- Preview in preferences page

**16.5 Smart Prioritization**
- Learn from user's tracking behavior
- Show most likely-to-bid opportunities first
- Personalized "Top picks for you" section
- De-prioritize opportunities user passed on before

---

## 17. New Feature Opportunities

### 17.1 Bid Calendar View
- Visual calendar showing all due dates
- Color-coded by category or status
- Click to view/track opportunity
- Export to external calendar

### 17.2 Competitive Intelligence
- Track which competitors bid on opportunities
- Award history analysis
- Market share estimates by category/agency
- Pricing intelligence (from public awards)

### 17.3 Proposal Templates
- Create reusable proposal sections
- Company boilerplate management
- Team template library
- Auto-fill from opportunity details

### 17.4 Document Management
- Upload and organize bid documents
- Version control for proposals
- Team document sharing
- Integration with Google Drive/Dropbox

### 17.5 Mobile App
- Native iOS/Android apps
- Push notifications for due dates
- Quick bid tracking on-the-go
- Offline opportunity viewing

### 17.6 API Access
- Public API for enterprise customers
- Webhook notifications
- Integration with CRM systems
- Zapier/Make.com integration

### 17.7 Analytics Dashboard
- Personal win rate tracking
- Revenue by category/agency
- Response time metrics
- Team performance comparisons

---

## 18. Feature Priority Matrix

| Feature | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Unsubscribe link | High (compliance) | Low | **Critical** |
| Classification feedback | High | Medium | **High** |
| Due date alerts | High | Low | **High** |
| Saved searches | Medium | Low | **High** |
| Full-text search | High | Medium | **High** |
| Notification preferences | Medium | Low | **Medium** |
| Team RBAC | Medium | Medium | **Medium** |
| Outcome tracking | Medium | Low | **Medium** |
| Calendar integration | Medium | Low | **Medium** |
| Recommendation engine | High | High | **Medium** |
| Mobile app | High | High | **Low** |
| Competitive intelligence | High | High | **Low** |

---

## 19. Technical Debt to Address

| Issue | Location | Recommendation |
|-------|----------|----------------|
| 191 print() statements | Multiple files | Replace with `logging` module |
| Dual preference tables | `users` + `user_preferences` | Consolidate to single table |
| No database indexes | `opportunities` table | Add indexes on `agency_name`, `due_date`, `status` |
| N+1 queries | `tracker_dashboard.py` | Use eager loading / JOINs |
| Hardcoded values | `billing.py:130-134` | Move to environment variables |
| No rate limiting | All API endpoints | Add `slowapi` middleware |

---

## 20. Implementation Roadmap

### Phase 1: Pre-Launch Critical (Week 1)
1. Add unsubscribe links to all emails
2. Add due date alert notifications
3. Fix all Heroku deployment issues
4. Add basic engagement tracking

### Phase 2: Core Enhancements (Weeks 2-4)
1. Implement full-text search
2. Add saved searches
3. Build notification preference center
4. Add outcome tracking for bids

### Phase 3: Collaboration Features (Weeks 5-8)
1. Implement team RBAC
2. Add team audit logging
3. Build team activity dashboard
4. Add calendar integration

### Phase 4: Intelligence Features (Weeks 9-12)
1. Build recommendation engine
2. Add classification feedback loop
3. Implement competitive intelligence
4. Build analytics dashboard

### Phase 5: Scale & Mobile (Months 4-6)
1. Public API development
2. Mobile app (React Native)
3. Advanced AI features
4. Enterprise integrations
