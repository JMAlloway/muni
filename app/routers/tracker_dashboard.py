# app/routers/tracker_dashboard.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from app.db_core import engine
from app.auth_utils import require_login
from app.routers._layout import page_shell

router = APIRouter(tags=["tracker"])

@router.get("/tracker/dashboard", response_class=HTMLResponse)
async def tracker_dashboard(request: Request):
    user_email = await require_login(request)
    if isinstance(user_email, RedirectResponse):
        print("[DEBUG dashboard] no session, redirecting to /login")
        return user_email
    print("[DEBUG dashboard] authenticated as", user_email)

    q = text("""
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
        rows = await conn.exec_driver_sql(q, {"email": user_email})
        items = [dict(r._mapping) for r in rows.fetchall()]

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

      <div id="tracked-grid" class="tracked-grid" data-items='{items}'></div>
    </section>

    <!-- Overlay + drawer used by your existing vendor.js -->
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

    <!-- Load vendor.js BEFORE tracker_dashboard.js so openVendorGuide is defined -->
    <script src="/static/vendor.js"></script>
    <script src="/static/bid_tracker.js"></script>
    <script src="/static/tracker_dashboard.js"></script>
    """
    return HTMLResponse(page_shell(body, title="Muni Alerts – My Bids", user_email=user_email))
