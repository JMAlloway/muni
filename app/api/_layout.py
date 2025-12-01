# app/routers/_layout.py

from typing import Dict, Optional
import sqlite3
import os
from urllib.parse import urlparse
from app.core.settings import settings

def _nav_links_html(user_email: Optional[str]) -> str:
    # Match Homepage_test /opportunities sidebar markup/icons
    return """
        <a href="/" class="nav-link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          <span class="nav-text">Home</span>
        </a>
        <a href="/opportunities" class="nav-link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
          <span class="nav-text">Discover Bids</span>
        </a>
        <a href="/tracker/dashboard" class="nav-link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="3" y="3" width="7" height="7"/>
            <rect x="14" y="3" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/>
          </svg>
          <span class="nav-text">My Dashboard</span>
        </a>
        <a href="/documents" class="nav-link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span class="nav-text">Documents</span>
        </a>
        <a href="/calendar" class="nav-link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/>
            <line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <span class="nav-text">Calendar</span>
        </a>
        <a href="/account" class="nav-link">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span class="nav-text">My Account</span>
        </a>
        """


def _account_links_html() -> str:
    return """
        <div class="nav-label" style="margin-top: 24px;">ACCOUNT</div>
        <nav class="navlinks">
            <a href="/account" class="nav-link">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
              <span class="nav-text">Settings</span>
            </a>
            <a href="/support" class="nav-link">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <circle cx="12" cy="12" r="10"/>
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <span class="nav-text">Support</span>
            </a>
        </nav>
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
    if not db_url.startswith("sqlite"):
        return default
    try:
        # Normalize path for sqlite+aiosqlite:///./muni_local.db
        if db_url.startswith("sqlite+aiosqlite:///"):
            db_path = db_url.split(":///")[-1]
        else:
            parsed = urlparse(db_url.replace("sqlite+aiosqlite", "sqlite"))
            db_path = parsed.path
            if db_path.startswith("//"):
                db_path = db_path[1:]
        db_path = os.path.abspath(db_path)
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "SELECT id, team_id, COALESCE(Tier, tier) FROM users WHERE lower(email) = lower(?) LIMIT 1",
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
                tcur = conn.execute(
                    """
                    SELECT t.name, COALESCE(u.Tier, u.tier) AS owner_tier
                    FROM teams t
                    LEFT JOIN users u ON u.id = t.owner_user_id
                    WHERE t.id = ?
                    LIMIT 1
                    """,
                    (team_id,),
                )
                trow = tcur.fetchone()
                if trow:
                    team_name = trow[0] or "Team"
                    owner_tier = _normalize_tier(trow[1])
                    if _TIER_ORDER.get(owner_tier.lower(), 0) > _TIER_ORDER.get(user_tier.lower(), 0):
                        effective_tier = owner_tier
                        via_team = True
                try:
                    ccur = conn.execute(
                        "SELECT COUNT(*) FROM team_members WHERE team_id = ? AND (accepted_at IS NOT NULL OR role = 'owner')",
                        (team_id,),
                    )
                    crow = ccur.fetchone()
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
            try:
                print(
                    f"[tier lookup] email={user_email} tier={effective_tier} label={label} via_team={via_team} db={db_path}"
                )
            except Exception:
                pass
            return info
        finally:
            conn.close()
    except Exception:
        return default


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
<link rel="stylesheet" href="/static/css/base.css">
<link rel="stylesheet" href="/static/css/pages.css">
</head>
<body>
<div class="app-shell">
    <aside class="sidebar">
        <div class="brand">
            <svg width="36" height="36" viewBox="0 0 40 40" fill="none" aria-hidden="true">
              <rect width="40" height="40" rx="12" fill="url(#grad1)"/>
              <path d="M10 20L17 27L30 13" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
              <defs>
                <linearGradient id="grad1" x1="0" y1="0" x2="40" y2="40">
                  <stop offset="0%" stop-color="#126a45"/>
                  <stop offset="100%" stop-color="#22c55e"/>
                </linearGradient>
              </defs>
            </svg>
            <span>EasyRFP</span>
        </div>
        <div class="nav-label">Main Menu</div>
        <nav class="navlinks">
            __NAV__
        </nav>
        __ACCOUNT__
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
            <img src="/static/img/bell.png" alt="" class="icon-img"><span class="notif-dot" aria-hidden="true"></span>
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
        .replace("__ACCOUNT__", _account_links_html())
        .replace("__TIER__", user_tier)
        .replace("__TEAM_BADGE__", team_badge)
        .replace("__AVATAR__", (user_email or "U")[:2].upper())
        .replace("__BODY__", body_html)
        .replace("__NOTIF_JS__", notif_js)
    )
    return html


def marketing_shell(body_html: str, title: str, user_email: Optional[str]) -> str:
    """
    Lightweight landing-page shell (no sidebar) styled by marketing.css.
    """
    # Always send primary CTA to signup to avoid jumping users past the flow.
    cta_url = "/signup"
    login_url = "/login?next=/tracker/dashboard"  # always go to login first
    hero_cta = "Sign Up"
    template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>__TITLE__</title>
  <link rel="stylesheet" href="/static/css/base.css">
  <link rel="stylesheet" href="/static/css/marketing.css">
</head>
<body class="marketing-body">
  <nav class="navbar">
    <div class="nav-container">
      <div class="nav-brand">
        <svg class="logo-icon" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="40" height="40" rx="10" fill="url(#gradient)"/>
          <path d="M10 20L17 27L30 13" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
          <defs>
            <linearGradient id="gradient" x1="0" y1="0" x2="40" y2="40">
              <stop offset="0%" stop-color="#126a45"/>
              <stop offset="100%" stop-color="#0f8b5a"/>
            </linearGradient>
          </defs>
        </svg>
        <span class="brand-text">EasyRFP</span>
      </div>
      <button class="nav-toggle" aria-label="Toggle navigation">
        <span></span><span></span><span></span>
      </button>
      <div class="nav-links">
        <a href="#features" class="nav-link">Features</a>
        <a href="#coverage" class="nav-link">Coverage</a>
        <a href="#pricing" class="nav-link">Pricing <span class="dropdown-arrow">∨</span></a>
        <a href="#details" class="nav-link">Resources</a>
        <a href="#contact" class="nav-link">Help</a>
      </div>
      <div class="nav-actions">
        <a href="__LOGIN_URL__" class="btn-ghost">Log In</a>
        <a href="__CTA_URL__" class="btn-primary">__HERO_CTA__</a>
      </div>
    </div>
  </nav>

  <main>
    __BODY__
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-brand">
          <svg class="logo-icon" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="40" height="40" rx="10" fill="url(#gradient2)"/>
            <path d="M10 20L17 27L30 13" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
            <defs>
              <linearGradient id="gradient2" x1="0" y1="0" x2="40" y2="40">
                <stop offset="0%" stop-color="#126a45"/>
                <stop offset="100%" stop-color="#0f8b5a"/>
              </linearGradient>
            </defs>
          </svg>
          <span class="brand-text">EasyRFP</span>
        </div>
        <div class="footer-links">
          <a href="/privacy" class="footer-link">Privacy</a>
          <span class="footer-dot">&middot;</span>
          <a href="/terms" class="footer-link">Terms</a>
          <span class="footer-dot">&middot;</span>
          <a href="#contact" class="footer-link">Contact</a>
          <span class="footer-dot">&middot;</span>
          <a href="#coverage" class="footer-link">Request Portal</a>
        </div>
      </div>
    </div>
  </footer>

  <script src="/static/js/marketing.js"></script>
</body>
</html>
    """
    return (
        template.replace("__TITLE__", title)
        .replace("__BODY__", body_html)
        .replace("__CTA_URL__", cta_url)
        .replace("__LOGIN_URL__", login_url)
        .replace("__HERO_CTA__", hero_cta)
    )


def auth_shell(body_html: str, title: str, wrapper_class: str = "", card_class: str = "") -> str:
    """
    Minimal shell for auth pages (no sidebar/top nav), keeps brand.
    """
    wrapper_cls = f"auth-wrapper {wrapper_class}".strip()
    card_cls = f"auth-card {card_class}".strip()
    template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>__TITLE__</title>
  <link rel="stylesheet" href="/static/css/base.css">
  <link rel="stylesheet" href="/static/css/auth.css">
</head>
<body class="auth-body">
  <div class="__WRAPPER__">
    <div class="auth-brand">
      <svg class="logo-icon" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="40" height="40" rx="10" fill="url(#gradient)"/>
        <path d="M10 20L17 27L30 13" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
        <defs>
          <linearGradient id="gradient" x1="0" y1="0" x2="40" y2="40">
            <stop offset="0%" stop-color="#126a45"/>
            <stop offset="100%" stop-color="#0f8b5a"/>
          </linearGradient>
        </defs>
      </svg>
      <span class="brand-text">EasyRFP</span>
    </div>
    <div class="__CARD__">
      __BODY__
    </div>
    <div class="auth-footer-links">
      <a href="/">Back to homepage</a>
      <span>&middot;</span>
      <a href="/privacy">Privacy</a>
      <span>&middot;</span>
      <a href="/terms">Terms</a>
    </div>
  </div>
</body>
</html>
    """
    return (
        template.replace("__TITLE__", title)
        .replace("__BODY__", body_html)
        .replace("__WRAPPER__", wrapper_cls)
        .replace("__CARD__", card_cls)
    )
