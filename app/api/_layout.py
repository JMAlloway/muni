# app/routers/_layout.py

from typing import Dict, Optional
import sqlite3
import os
import logging
from urllib.parse import urlparse
from app.core.settings import settings

logger = logging.getLogger(__name__)

# PostgreSQL support - import psycopg2 if available
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

def _nav_links_html(user_email: Optional[str]) -> str:
    if user_email:
        return """
        <a href="/" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-overview.png" alt=""></span><span class="nav-text">Overview</span></a>
        <a href="/opportunities" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-opportunities.png" alt=""></span><span class="nav-text">Open Opportunities</span></a>
        <a href="/tracker/dashboard" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-dashboard.png" alt=""></span><span class="nav-text">My Dashboard</span></a>
        <a href="/account" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-account.png" alt=""></span><span class="nav-text">My Account</span></a>
        """
    else:
        return """
        <a href="/" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-home.png" alt=""></span><span class="nav-text">Home</span></a>
        <a href="/signup" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-signup.png" alt=""></span><span class="nav-text">Sign up</span></a>
        <a href="/login" class="nav-link"><span class="nav-icon" aria-hidden="true"><img src="/static/nav-login.png" alt=""></span><span class="nav-text">Sign in</span></a>
        """


_TIER_ORDER = {"free": 0, "starter": 1, "professional": 2, "enterprise": 3}


def _normalize_tier(raw: Optional[str]) -> str:
    mapping = {
        "free": "Free",
        "starter": "Starter",
        "professional": "Professional",
        "enterprise": "Enterprise",
    }
    key = (raw or "Free").strip().lower()
    return mapping.get(key, "Free")


def _get_user_tier_info(user_email: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Best-effort effective tier lookup for the header badge and billing.
    Returns a dict with keys: effective, label, source, team_id, team_name, team_member_count.
    Supports both SQLite (local) and PostgreSQL (Heroku).
    """
    default = {
        "effective": "Free",
        "label": "Free",
        "source": "self",
        "team_id": None,
        "team_name": None,
        "team_member_count": 0,
        "user_id": None,
    }
    if not user_email:
        return default
    db_url = settings.DB_URL or ""

    try:
        # Determine database type and get connection
        if db_url.startswith("sqlite") or db_url.startswith("sqlite+aiosqlite"):
            conn = _get_sqlite_connection(db_url)
            placeholder = "?"
        elif ("postgresql" in db_url or "postgres" in db_url) and HAS_PSYCOPG2:
            conn = _get_postgres_connection(db_url)
            placeholder = "%s"
        else:
            return default

        try:
            cur = conn.cursor()
            # PostgreSQL is case-sensitive with column names, use lowercase
            cur.execute(
                f"SELECT id, team_id, tier FROM users WHERE lower(email) = lower({placeholder}) LIMIT 1",
                (user_email,),
            )
            row = cur.fetchone()
            if not row:
                return default
            user_id, team_id, raw_tier = row
            user_tier = _normalize_tier(raw_tier)

            team_name = None
            team_member_count = 0
            effective_tier = user_tier
            via_team = False

            if team_id:
                # Pull owner tier + team name
                cur.execute(
                    f"""
                    SELECT t.name, u.tier AS owner_tier
                    FROM teams t
                    LEFT JOIN users u ON u.id = t.owner_user_id
                    WHERE t.id = {placeholder}
                    LIMIT 1
                    """,
                    (team_id,),
                )
                trow = cur.fetchone()
                if trow:
                    team_name = trow[0] or "Team"
                    owner_tier = _normalize_tier(trow[1])
                    if _TIER_ORDER.get(owner_tier.lower(), 0) > _TIER_ORDER.get(user_tier.lower(), 0):
                        effective_tier = owner_tier
                        via_team = True
                try:
                    cur.execute(
                        f"SELECT COUNT(*) FROM team_members WHERE team_id = {placeholder} AND (accepted_at IS NOT NULL OR role = 'owner')",
                        (team_id,),
                    )
                    crow = cur.fetchone()
                    team_member_count = int(crow[0]) if crow and crow[0] is not None else 0
                except Exception:
                    team_member_count = 0

            label = f"{effective_tier} (via Team)" if via_team else effective_tier
            info = {
                "effective": effective_tier,
                "label": label,
                "source": "team" if via_team else "self",
                "team_id": team_id,
                "team_name": team_name,
                "team_member_count": team_member_count,
                "user_id": user_id,
            }
            # Use proper logging instead of print
            logger.debug(
                f"Tier lookup: email={user_email[:3]}*** tier={effective_tier} via_team={via_team}"
            )
            return info
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Tier lookup failed: {e}")
        return default


def _get_sqlite_connection(db_url: str):
    """Get a SQLite connection from the database URL."""
    if db_url.startswith("sqlite+aiosqlite:///"):
        db_path = db_url.split(":///")[-1]
    else:
        parsed = urlparse(db_url.replace("sqlite+aiosqlite", "sqlite"))
        db_path = parsed.path
        if db_path.startswith("//"):
            db_path = db_path[1:]
    db_path = os.path.abspath(db_path)
    return sqlite3.connect(db_path)


def _get_postgres_connection(db_url: str):
    """Get a PostgreSQL connection from the database URL."""
    # Convert async URL to sync format for psycopg2
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(sync_url)


def _get_user_tier(user_email: Optional[str]) -> str:
    """Compatibility wrapper used by older views; returns the effective label."""
    return _get_user_tier_info(user_email).get("label", "Free")


def page_shell(body_html: str, title: str, user_email: Optional[str]) -> str:
    """
    Shared shell for all pages.
    user_email:
      - None if anonymous
      - "someone@company.com" if logged in
    """

    nav_links = _nav_links_html(user_email)
    tier_info = _get_user_tier_info(user_email)
    user_tier = tier_info.get("label", "Free")
    team_badge = ""
    if tier_info.get("source") == "team":
        team_badge = '<span class="team-badge">via team</span>'

    notif_js = r"""
// notifications drawer (dynamic)
(function(){
  const btn = document.getElementById('notif-btn');
  const drawer = document.getElementById('notif-drawer');
  const overlay = document.getElementById('notif-overlay');
  const closeBtn = document.getElementById('notif-close');
  const list = document.getElementById('notif-list');
  const badge = document.querySelector('.notif-dot');
  if (!btn || !drawer || !overlay || !list) return;
  const getCSRF = () => (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||[])[1] || "";
  const esc = (s) => (s==null?"":String(s)).replace(/[&<>"']/g, c=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]||c));
  let notifications = [];

  const updateBadge = (count) => {
    if (!badge) return;
    if (count > 0) {
      badge.style.display = 'inline-flex';
      badge.textContent = count > 99 ? '99+' : String(count);
    } else {
      badge.style.display = 'none';
      badge.textContent = '';
    }
  };

  const timeAgo = (iso) => {
    if (!iso) return '';
    try {
      const then = new Date(iso).getTime();
      const now = Date.now();
      const diff = Math.max(0, now - then) / 1000;
      if (diff < 60) return 'Just now';
      if (diff < 3600) return Math.floor(diff/60)+'m ago';
      if (diff < 86400) return Math.floor(diff/3600)+'h ago';
      return Math.floor(diff/86400)+'d ago';
    } catch(_) { return ''; }
  };

  const render = () => {
    if (!notifications.length) {
      list.innerHTML = "<div class='notif-item muted'>No notifications yet.</div>";
      return;
    }
    list.innerHTML = notifications.map((n) => {
      const unread = !n.read_at;
      const inviteActions = (n.type === 'team_invite' && !n.actioned_at)
        ? `<div class="notif-actions">
            <button class="notif-btn accept" data-action="accept" data-id="${n.id}">Accept</button>
            <button class="notif-btn decline" data-action="decline" data-id="${n.id}">Decline</button>
           </div>`
        : '';
      const pill = unread ? '<span class="notif-pill">New</span>' : '<span class="notif-pill muted">Seen</span>';
      return `
        <div class="notif-item ${unread ? 'unread' : ''}">
          <div class="notif-line">
            ${pill}
            <span class="notif-time">${timeAgo(n.created_at)}</span>
          </div>
          <div class="notif-body"><strong>${esc(n.title||'')}</strong><br>${esc(n.body||'')}</div>
          ${inviteActions}
        </div>
      `;
    }).join('');
  };

  const fetchNotifs = async () => {
    try {
      const res = await fetch('/api/notifications', { credentials:'include' });
      if (!res.ok) return;
      const data = await res.json();
      notifications = data.notifications || [];
      updateBadge(data.unread_count || 0);
      render();
    } catch(_) {}
  };

  const markAllRead = async () => {
    try {
      const unread = notifications.filter(n => !n.read_at);
      await Promise.all(unread.map(n => fetch(`/api/notifications/${n.id}/read`, {
        method:'POST',
        credentials:'include',
        headers: { 'X-CSRF-Token': getCSRF() }
      })));
      notifications = notifications.map(n => Object.assign({}, n, { read_at: n.read_at || new Date().toISOString() }));
      updateBadge(0);
      render();
    } catch(_) {}
  };

  const toggle = (open) => {
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (open) {
      fetchNotifs().then(markAllRead);
    }
  };

  list.addEventListener('click', async function(e){
    const btnEl = e.target.closest('[data-action][data-id]');
    if (!btnEl) return;
    const action = btnEl.getAttribute('data-action');
    const id = btnEl.getAttribute('data-id');
    try {
      const res = await fetch(`/api/notifications/${id}/action`, {
        method:'POST',
        credentials:'include',
        headers: { 'Content-Type':'application/json', 'X-CSRF-Token': getCSRF() },
        body: JSON.stringify({ action })
      });
      if (!res.ok) return;
      if (action === 'accept') {
        window.location.reload();
        return;
      }
      await fetchNotifs();
    } catch(_) {}
  });

  btn.addEventListener('click', function(){ toggle(true); });
  if (closeBtn) closeBtn.addEventListener('click', function(){ toggle(false); });
  overlay.addEventListener('click', function(){ toggle(false); });

  // Initial load + polling
  fetchNotifs();
  setInterval(fetchNotifs, 30000);
})();
"""

    template = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>__TITLE__</title>
<link rel="stylesheet" href="/static/base.css">
</head>
<body>
<div class="app-shell">
    <aside class="sidebar">
        <div class="brand">
            <img src="/static/logo.png" alt="EasyRFP" />
            <span>EasyRFP</span>
        </div>
        <div class="nav-label">Navigation</div>
        <nav class="navlinks">
            __NAV__
        </nav>
    </aside>
    <div class="content">
        <div class="topbar" role="banner">
    <div class="topbar-left">
        <a class="top-pill top-home" href="/" aria-label="Home">
            <span class="top-home-icon" aria-hidden="true"></span>
            <span class="top-label">Home</span>
        </a>
        <span class="top-pill top-tier" role="status">
            <span class="top-label">Tier:</span> <strong>__TIER__</strong> __TEAM_BADGE__
            <a href="/billing" class="top-upgrade">Upgrade</a>
        </span>
    </div>
    <div class="topbar-right">
        <button class="icon-btn" type="button" aria-label="Notifications" id="notif-btn">
            <img src="/static/bell.png" alt="" class="icon-img"><span class="notif-dot" aria-hidden="true"></span>
        </button>
        <div class="top-dropdown">
            <button class="icon-btn" type="button" aria-label="Help" id="help-btn">?</button>
            <div class="top-menu" id="help-menu" role="menu">
                <a href="/privacy" role="menuitem">Privacy Policy</a>
                <a href="/terms" role="menuitem">Terms of Service</a>
            </div>
        </div>
        <div class="top-dropdown">
            <button class="avatar-button" type="button" aria-haspopup="menu" aria-expanded="false" id="avatar-btn">
                <span class="avatar-halo">
                    <span class="avatar-circle">__AVATAR__</span>
                </span>
                <span class="top-caret" aria-hidden="true">&gt;</span>
            </button>
            <div class="top-menu" id="avatar-menu" role="menu">
                <a href="/account" role="menuitem">My Account</a>
                <a href="/account/preferences" role="menuitem">Preferences</a>
                <a href="/billing" role="menuitem">Account Billing</a>
                <a href="/logout" role="menuitem">Logout</a>
            </div>
        </div>
    </div>
</div>
        <main class="page">
        __BODY__
        </main>
    </div>
</div>
<button class="sidebar-toggle" id="sidebar-toggle" aria-label="Toggle sidebar">&lt;&lt;</button>

<div id="notif-overlay" aria-hidden="true"></div>
<aside id="notif-drawer" aria-hidden="true">
  <header>
    <div>
      <div class="notif-title">Notifications</div>
      <div class="notif-sub">Inbox • Last 14 days</div>
    </div>
    <button class="icon-btn" id="notif-close" type="button" aria-label="Close notifications">x</button>
  </header>
  <div class="notif-list" id="notif-list"></div>
</aside>

<script>
__NOTIF_JS__

// help dropdown
(function(){
  const btn = document.getElementById('help-btn');
  const menu = document.getElementById('help-menu');
  if (!btn || !menu) return;
  const toggle = (open) => {
    menu.style.display = open ? 'block' : 'none';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  btn.addEventListener('click', function(){
    const isOpen = menu.style.display === 'block';
    toggle(!isOpen);
  });
  document.addEventListener('click', function(e){
    if (!btn.contains(e.target) && !menu.contains(e.target)) toggle(false);
  });
})();


// avatar dropdown
(function(){
  const btn = document.getElementById('avatar-btn');
  const menu = document.getElementById('avatar-menu');
  if (!btn || !menu) return;
  const toggle = (open) => {
    menu.style.display = open ? 'block' : 'none';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  btn.addEventListener('click', function(){
    const isOpen = menu.style.display === 'block';
    toggle(!isOpen);
  });
  document.addEventListener('click', function(e){
    if (!btn.contains(e.target) && !menu.contains(e.target)) toggle(false);
  });
})();


// sidebar toggle
(function(){
  const btn = document.getElementById('sidebar-toggle');
  if (!btn) return;
  btn.addEventListener('click', function(){
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    btn.textContent = collapsed ? '>>' : '<<';
  });
})();

</script>


</body>
</html>

    """
    html = (
        template.replace("__TITLE__", title)
        .replace("__NAV__", nav_links)
        .replace("__TIER__", user_tier)
        .replace("__TEAM_BADGE__", team_badge)
        .replace("__AVATAR__", (user_email or "U")[:2].upper())
        .replace("__BODY__", body_html)
        .replace("__NOTIF_JS__", notif_js)
    )
    return html