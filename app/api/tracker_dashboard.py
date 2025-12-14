"""Dashboard view for tracked solicitations."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.api._layout import page_shell


router = APIRouter(prefix="/tracker", tags=["dashboard"])

# Basic color palette used for avatars and accents (kept small for consistency)
_AVATAR_COLORS = [
    "#126a45",
    "#2563eb",
    "#7c3aed",
    "#0f766e",
    "#f59e0b",
    "#ef4444",
    "#0ea5e9",
    "#10b981",
]


def _initials(email: str) -> str:
    handle = (email or "").split("@")[0]
    clean = handle.replace(".", " ").replace("_", " ").strip()
    parts = [p for p in clean.split(" ") if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (handle[:2] or "??").upper()


def _color_for(email: str, idx: Optional[int] = None) -> str:
    """
    Stable color for each user.
    If idx is provided, prefer palette index (matches team avatar order).
    Otherwise, hash the email to the palette.
    """
    if idx is not None:
        return _AVATAR_COLORS[idx % len(_AVATAR_COLORS)]
    h = int(hashlib.md5((email or "").encode("utf-8")).hexdigest(), 16)
    return _AVATAR_COLORS[h % len(_AVATAR_COLORS)]


def _start_of_week(now: dt.datetime) -> dt.datetime:
    monday = now - dt.timedelta(days=now.weekday())
    return dt.datetime(monday.year, monday.month, monday.day)


def _parse_dt(raw: Optional[str]) -> Optional[dt.datetime]:
    if not raw:
        return None
    s = str(raw)
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(s)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _format_due(d: Optional[dt.datetime]) -> str:
    if not d:
        return "TBD"
    return d.strftime("%b %d, %I:%M %p").upper()


def _esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


@router.get("/dashboard", include_in_schema=False)
async def tracker_dashboard(request: Request) -> HTMLResponse:
    user_email = get_current_user_email(request)
    if not user_email:
        return RedirectResponse("/login?next=/tracker/dashboard", status_code=303)

    async with engine.begin() as conn:
        user_row = await conn.exec_driver_sql(
            "SELECT id, email, team_id FROM users WHERE lower(email) = lower(:e) LIMIT 1",
            {"e": user_email},
        )
        user_data = user_row.first()

    if not user_data:
        return RedirectResponse("/login?next=/tracker/dashboard", status_code=303)

    user_id = user_data._mapping["id"]
    team_id = user_data._mapping.get("team_id")

    async with engine.begin() as conn:
        tracked_rows = await conn.exec_driver_sql(
            """
            SELECT
              t.user_id,
              u.email AS owner_email,
              t.opportunity_id,
              COALESCE(t.status, 'prospecting') AS status,
              COALESCE(t.notes, '') AS notes,
              t.created_at AS tracked_at,
              o.title,
              o.agency_name,
              o.external_id,
              o.due_date,
              COALESCE(o.ai_category, o.category) AS category,
              COALESCE(t.visibility, 'private') AS visibility,
              (
                SELECT COUNT(*)
                FROM bid_notes bn
                WHERE bn.team_id = :team_id AND bn.opportunity_id = o.id
              ) AS note_count,
              (SELECT COUNT(*) FROM user_uploads u WHERE u.opportunity_id = o.id) AS file_count
            FROM user_bid_trackers t
            JOIN opportunities o ON o.id = t.opportunity_id
            JOIN users u ON u.id = t.user_id
            WHERE
              (
                :team_id IS NOT NULL AND t.team_id = :team_id
              )
              OR (
                :team_id IS NULL AND t.user_id = :uid
              )
              OR (
                :team_id IS NOT NULL AND t.team_id IS NULL AND t.user_id = :uid
              )
            ORDER BY (o.due_date IS NULL) ASC, o.due_date ASC, t.created_at DESC
            """,
            {"uid": user_id, "team_id": team_id},
        )
        tracked = [dict(r._mapping) for r in tracked_rows.fetchall()]

        team_members: List[Dict[str, str]] = []
        if team_id:
            team_res = await conn.exec_driver_sql(
                """
                SELECT u.email
                FROM team_members tm
                JOIN users u ON u.id = tm.user_id
                WHERE tm.team_id = :t
                  AND (tm.accepted_at IS NOT NULL OR tm.role = 'owner')
                ORDER BY tm.invited_at ASC
                """,
                {"t": team_id},
            )
            team_members = [{"email": r._mapping["email"]} for r in team_res.fetchall()]

        uploads_rows = await conn.exec_driver_sql(
            """
            SELECT u.filename, u.created_at, u.user_id, o.title, usr.email AS owner_email
            FROM user_uploads u
            JOIN opportunities o ON o.id = u.opportunity_id
            JOIN users usr ON usr.id = u.user_id
            WHERE
              (
                :team_id IS NOT NULL AND usr.team_id = :team_id
              )
              OR (
                usr.team_id IS NULL AND u.user_id = :uid
              )
            ORDER BY u.created_at DESC
            LIMIT 40
            """,
            {"uid": user_id, "team_id": team_id},
        )
        uploads = [dict(r._mapping) for r in uploads_rows.fetchall()]

    now = dt.datetime.utcnow()
    total_items = len(tracked)
    week_start = _start_of_week(now)
    tracked_this_week = sum(
        1
        for it in tracked
        if it.get("tracked_at") and dt.datetime.fromisoformat(str(it["tracked_at"])) >= week_start
    )
    due_soon_count = 0
    won_count = 0
    status_counts = {"active": 0, "won": 0, "pending": 0, "review": 0}
    upcoming_items = []
    for it in tracked:
        status = (it.get("status") or "prospecting").lower()
        if status == "won":
            won_count += 1
        if status in ("deciding", "drafting"):
            status_counts["pending"] += 1
        elif status in ("submitted", "review"):
            status_counts["review"] += 1
        elif status == "won":
            status_counts["won"] += 1
        else:
            status_counts["active"] += 1

        due_raw = it.get("due_date")
        due_dt = _parse_dt(due_raw)

        if due_dt:
            day_gap = (due_dt.date() - now.date()).days
            if 0 <= day_gap <= 7:
                due_soon_count += 1
            upcoming_items.append(
                {
                    "title": it.get("title") or "Untitled",
                    "agency": it.get("agency_name") or "",
                    "external_id": it.get("external_id") or "",
                    "due_iso": due_dt.isoformat(),
                    "due_display": _format_due(due_dt),
                    "day_gap": day_gap,
                }
            )

    if not upcoming_items:
        for it in tracked:
            due_dt = _parse_dt(it.get("due_date"))
            if due_dt and (due_dt.date() - now.date()).days >= 0:
                upcoming_items.append(
                    {
                        "title": it.get("title") or "Untitled",
                        "agency": it.get("agency_name") or "",
                        "external_id": it.get("external_id") or "",
                        "due_iso": due_dt.isoformat(),
                        "due_display": _format_due(due_dt),
                        "day_gap": (due_dt.date() - now.date()).days,
                    }
                )
    upcoming_items.sort(key=lambda x: x["due_iso"])
    upcoming_json = json.dumps(upcoming_items)

    items_json = json.dumps(tracked, default=str)

    # Activity feed (best-effort)
    activity_entries: List[Dict[str, str]] = []
    for it in tracked:
        ts = it.get("tracked_at")
        try:
            when = dt.datetime.fromisoformat(str(ts)) if ts else now
        except Exception:
            when = now
        activity_entries.append(
            {
                "who": it.get("owner_email") or user_email,
                "verb": "added to tracking",
                "obj": it.get("title") or "Untitled",
                "when": when.isoformat(),
            }
        )

    for up in uploads:
        try:
            when = dt.datetime.fromisoformat(str(up.get("created_at"))) if up.get("created_at") else now
        except Exception:
            when = now
        activity_entries.append(
            {
                "who": up.get("owner_email") or user_email,
                "verb": f"uploaded {up.get('filename') or 'a file'}",
                "obj": up.get("title") or "",
                "when": when.isoformat(),
            }
        )

    activity_entries.sort(key=lambda x: x["when"], reverse=True)
    activity_entries = activity_entries[:12]

    member_list = team_members or [{"email": user_email}]
    email_to_idx = {
        (m.get("email") or "").lower(): idx for idx, m in enumerate(member_list)
    }

    def render_activity() -> str:
        verb_icons = {
            "added to tracking": "📋",
            "uploaded": "📤",
            "completed": "✅",
            "awarded": "🎉",
            "submitted": "🚀",
        }

        blocks = []
        for entry in activity_entries:
            who = entry.get("who") or ""
            name = who.split("@")[0] or "User"
            verb = entry.get("verb") or ""

            icon = "📋"
            for key, emoji in verb_icons.items():
                if key in verb.lower():
                    icon = emoji
                    break

            blocks.append(
                f"""
                <div class="activity-item">
                  <div class="activity-icon">{icon}</div>
                  <div class="activity-content">
                    <div class="activity-text"><strong>{_esc(name)}</strong> {_esc(verb)} {_esc(entry.get('obj'))}</div>
                    <div class="activity-time">Just now</div>
                  </div>
                </div>
                """
            )
        if not blocks:
            return '<div class="muted">No recent activity yet.</div>'
        return "\n".join(blocks)

    def render_team_bar() -> str:
        avatars = []
        palette_len = len(_AVATAR_COLORS)
        for idx, m in enumerate(member_list[:4]):
            em = m.get("email") or ""
            color = _AVATAR_COLORS[idx % palette_len]
            avatars.append(f'<div class="team-avatar" style="background:{color};">{_esc(_initials(em))}</div>')
        avatars.append('<a class="team-avatar add" href="/account/team">+</a>')
        count = len(member_list)
        return f"""
        <div class="team-bar fade-in">
          <div class="team-info">
            <div class="team-avatars">{''.join(avatars)}</div>
            <div class="team-details">
              <span class="team-label">Your Team</span>
              <span><strong>Team workspace</strong> · {count} member{'s' if count != 1 else ''}</span>
            </div>
          </div>
          <a class="shared-dashboard-btn" href="/account/team">
            <span>⇱</span>
            Team Dashboard
          </a>
        </div>
        """

    stats_html = f"""
    <div class="stats-grid">
      <div class="stat-card featured fade-in stagger-1">
        <div class="stat-icon">dY"^</div>
        <div class="stat-label">Active Bids</div>
        <div class="stat-value"><span class="counter" data-target="{total_items}">0</span></div>
        <span class="stat-change positive">+{tracked_this_week} this week</span>
      </div>
      <div class="stat-card fade-in stagger-2">
        <div class="stat-icon">?</div>
        <div class="stat-label">Due This Week</div>
        <div class="stat-value"><span class="counter" data-target="{due_soon_count}">0</span></div>
        <span class="stat-change negative">{due_soon_count} urgent</span>
      </div>
      <div class="stat-card fade-in stagger-3">
        <div class="stat-icon">?o.</div>
        <div class="stat-label">Won This Quarter</div>
        <div class="stat-value"><span class="counter" data-target="{won_count}">0</span></div>
        <span class="stat-change positive">+0 vs Q3</span>
      </div>
      <div class="stat-card fade-in stagger-4">
        <div class="stat-icon">dY'?</div>
        <div class="stat-label">Pipeline Value</div>
        <div class="stat-value">$<span class="counter" data-target="2.4">0</span>M</div>
        <span class="stat-change positive">$340K added</span>
      </div>
    </div>
    """


    timeline_html = f"""
    <div class="timeline-section fade-in stagger-2">
      <div class="timeline-header">
        <div>
          <h3 class="section-title">Upcoming Deadlines</h3>
          <p class="section-subtitle" id="timeline-range">Next 7 days</p>
        </div>
        <div class="section-tabs" id="timeline-toggle">
          <button class="section-tab active" data-range="week">Week</button>
          <button class="section-tab" data-range="month">Month</button>
          <button class="section-tab" data-range="all">All</button>
        </div>
      </div>
      <div class="timeline" id="timeline"></div>
      <script id="upcoming-data" type="application/json">{upcoming_json}</script>
    </div>
    """

    circumference = 440
    seg_total = max(1, sum(status_counts.values()))
    def seg_len(n: int) -> float:
        return (n / seg_total) * circumference
    active_len = seg_len(status_counts["active"])
    won_len = seg_len(status_counts["won"])
    pending_len = seg_len(status_counts["pending"])
    review_len = seg_len(status_counts["review"])
    donut_html = f"""
    <div class="chart-card fade-in stagger-3">
      <div class="chart-header">
        <h3 class="chart-title">Bid Status Overview</h3>
      </div>
      <div class="donut-chart">
        <svg viewBox="0 0 200 200">
          <circle class="donut-segment" cx="100" cy="100" r="70"
                  stroke="#126a45" stroke-dasharray="{active_len} {circumference}" stroke-dashoffset="0"/>
          <circle class="donut-segment" cx="100" cy="100" r="70"
                  stroke="#22c55e" stroke-dasharray="{won_len} {circumference}" stroke-dashoffset="-{active_len}"/>
          <circle class="donut-segment" cx="100" cy="100" r="70"
                  stroke="#f59e0b" stroke-dasharray="{pending_len} {circumference}" stroke-dashoffset="-{active_len + won_len}"/>
          <circle class="donut-segment" cx="100" cy="100" r="70"
                  stroke="#3b82f6" stroke-dasharray="{review_len} {circumference}" stroke-dashoffset="-{active_len + won_len + pending_len}"/>
        </svg>
        <div class="donut-center">
          <div class="donut-value">{total_items}</div>
          <div class="donut-label">Total Bids</div>
        </div>
      </div>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-dot" style="background:#126a45;"></span> Active ({status_counts['active']})</div>
        <div class="legend-item"><span class="legend-dot" style="background:#22c55e;"></span> Won ({status_counts['won']})</div>
        <div class="legend-item"><span class="legend-dot" style="background:#f59e0b;"></span> Pending ({status_counts['pending']})</div>
        <div class="legend-item"><span class="legend-dot" style="background:#3b82f6;"></span> Review ({status_counts['review']})</div>
      </div>
    </div>
    """

    activity_html = f"""
    <div class="activity-feed fade-in stagger-4">
      <h3 class="section-title">Recent Activity</h3>
      <div class="activity-items">
        {render_activity()}
      </div>
    </div>
    """

    filters_html = """
    <div class="filters">
      <div class="filter-group">
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
        </select>
        <select id="sort-by">
          <option value="soonest">Soonest due</option>
          <option value="latest">Latest due</option>
          <option value="alpha">A to Z</option>
          <option value="manual">Manual</option>
        </select>
        <input id="search-filter" type="search" placeholder="Search title, ID, agency"/>
      </div>
      <button id="reset-filters" class="reset-btn" type="button">Reset</button>
    </div>
    <div id="summary-count" class="section-subtitle"></div>
    """

    drawer_members_html = "".join(
        f'<div class="drawer-avatar" style="background:{_color_for(m.get("email") or "", idx)};">{_esc(_initials(m.get("email") or ""))}</div>'
        for idx, m in enumerate(member_list[:3])
    )
    drawer_member_count = f'{len(member_list)} member{"s" if len(member_list) != 1 else ""}'
    thread_html = f"""
    <div class="drawer-overlay" id="drawerOverlay"></div>
    <div class="chat-drawer" id="chatDrawer" aria-hidden="true">
      <div class="drawer-header">
        <div class="drawer-header-top">
          <button class="drawer-close-btn" id="drawerCloseBtn" type="button" aria-label="Close chat">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
          <div class="drawer-title-area">
            <div class="drawer-label">Team Thread</div>
            <div class="drawer-title" id="drawerTitle">Select a solicitation</div>
            <div class="drawer-subtitle" id="drawerSubtitle"></div>
          </div>
        </div>
        <div class="drawer-members" id="drawerMembers">
          {drawer_members_html}
          <span class="drawer-member-count">{drawer_member_count}</span>
        </div>
      </div>
      
      <div class="drawer-messages" id="drawerMessages">
        <div class="drawer-date-divider" id="drawerEmpty">
          <span>Select a solicitation to view messages.</span>
        </div>
        <div class="drawer-typing" id="drawerTyping" style="display: none;">
          <div class="drawer-msg-avatar">...</div>
          <div class="drawer-typing-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
      
      <div class="drawer-input-area">
        <button class="drawer-attach-btn" type="button" aria-label="Attach">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
          </svg>
        </button>
        <input type="text" class="drawer-input" id="drawerInput" placeholder="Type a message...">
        <button class="drawer-emoji-btn" type="button" aria-label="Emoji">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M8 14s1.5 2 4 2 4-2 4-2"></path>
            <line x1="9" y1="9" x2="9.01" y2="9"></line>
            <line x1="15" y1="9" x2="15.01" y2="9"></line>
          </svg>
        </button>
        <button class="drawer-send-btn" id="drawerSendBtn" type="button" aria-label="Send">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </div>
    </div>
    """

    upload_html = """
    <div id="upload-overlay" aria-hidden="true"></div>
    <aside id="upload-drawer" aria-hidden="true">
      <header>
        <div>
          <div class="section-title" id="upload-title">Upload Documents</div>
          <div class="muted" id="upload-subtitle">Attach files to this solicitation</div>
        </div>
        <button id="upload-cancel" class="icon-btn" type="button">Close</button>
      </header>
      <form id="upload-form">
        <input type="hidden" name="opportunity_id" id="upload-oid" />
        <label class="muted">Choose files</label>
        <input type="file" id="upload-files" name="files" multiple />
        <button id="upload-submit" type="submit" class="action-btn primary" style="margin-top:12px;">Upload</button>
        <div class="muted" style="margin-top:8px;">Max size per file: 10MB. Supported common document types.</div>
      </form>
    </aside>
    """

    tracked_html = f"""
    <div class="section-header fade-in stagger-3">
      <div>
        <h2 class="section-title">My Tracked Solicitations</h2>
        <p class="section-subtitle">Status, files, and step-by-step guidance.</p>
      </div>
      <div id="summary-count-inline" class="section-subtitle"></div>
    </div>
    {filters_html}
    <div id="tracked-grid"
         class="solicitations-list tracked-grid"
         data-items='{_esc(items_json)}'
         data-user-email="{_esc(user_email)}"
         data-user-id="{user_id}"></div>
    """

    body_template = """
    <link rel="stylesheet" href="/static/css/dashboard.css">
    __TEAM_BAR__
    __STATS__
    <div class="grid-3">
      <div>
        __TIMELINE__
        __TRACKED__
      </div>
      <div>
        __DONUT__
        __ACTIVITY__
      </div>
    </div>
    __THREAD__
    __UPLOAD__
    <script>
      (function() {
        const timelineEl = document.getElementById('timeline');
        const toggle = document.getElementById('timeline-toggle');
        const rangeLabel = document.getElementById('timeline-range');
        const dataEl = document.getElementById('upcoming-data');
        if (!timelineEl || !dataEl) return;
        let data = [];
        try { data = JSON.parse(dataEl.textContent || '[]'); } catch(_) { data = []; }
        const render = (range) => {
          const now = new Date();
          const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
          const items = data.filter((d) => {
            const due = new Date(d.due_iso);
            const dueDay = new Date(due.getFullYear(), due.getMonth(), due.getDate());
            const diff = (dueDay - today) / 86400000;
            if (range === 'week') return diff >= 0 && diff <= 7;
            if (range === 'month') return diff >= 0 && diff <= 31;
            return diff >= 0;
          }).slice(0, 50);
          timelineEl.innerHTML = items.length ? items.map((it) => `
            <div class="timeline-item">
              <div class="timeline-dot"><span class="inner-dot"></span></div>
              <div class="timeline-content">
                <div class="timeline-date">${it.due_display || it.due_iso}</div>
                <div class="timeline-title">${it.title}</div>
                <div class="timeline-desc">${it.agency} ${it.external_id ? ' • ' + it.external_id : ''}</div>
              </div>
            </div>
          `).join('') : '<div class="timeline-empty muted">No upcoming deadlines.</div>';
          rangeLabel.textContent = range === 'week' ? 'Next 7 days' : (range === 'month' ? 'Next 30 days' : 'All upcoming');
        };
        render('week');
        toggle.addEventListener('click', (e) => {
          const btn = e.target.closest('button[data-range]');
          if (!btn) return;
          toggle.querySelectorAll('button').forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          render(btn.getAttribute('data-range'));
        });
      })();
    </script>
    <script>
      (function(){
        const counters = document.querySelectorAll('.counter[data-target]');
        counters.forEach((el) => {
          const target = parseFloat(el.getAttribute('data-target') || '0');
          const start = performance.now();
          const duration = 1200;
          const animate = (ts) => {
            const progress = Math.min(1, (ts - start) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            const val = target % 1 === 0 ? Math.round(target * eased) : (target * eased).toFixed(1);
            el.textContent = val;
            if (progress < 1) requestAnimationFrame(animate);
          };
          requestAnimationFrame(animate);
        });
      })();
    </script>
    <script src="/static/js/tracker_dashboard.js"></script>
    <script>
      (function(){
        if (document && document.body) document.body.classList.add('tracker-dashboard-page');
      }());
    </script>
    """

    body = (
        body_template.replace("__TEAM_BAR__", render_team_bar())
        .replace("__STATS__", stats_html)
        .replace("__TIMELINE__", timeline_html)
        .replace("__DONUT__", donut_html)
        .replace("__TRACKED__", tracked_html)
        .replace("__ACTIVITY__", activity_html)
        .replace("__THREAD__", thread_html)
        .replace("__UPLOAD__", upload_html)
    )

    return HTMLResponse(page_shell(body, "Tracker Dashboard", user_email))
