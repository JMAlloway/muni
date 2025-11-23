# app/routers/_layout.py

from typing import Optional
import sqlite3
import os
from urllib.parse import urlparse
from app.core.settings import settings

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


def _get_user_tier(user_email: Optional[str]) -> str:
    """Best-effort tier lookup for the header badge."""
    if not user_email:
        return "Free"
    db_url = settings.DB_URL or ""
    if not db_url.startswith("sqlite"):
        return "Free"
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
            # If column is stored as "Tier" vs "tier", select both.
            cur = conn.execute(
                "SELECT COALESCE(Tier, tier) FROM users WHERE lower(email) = lower(?) LIMIT 1",
                (user_email,),
            )
            row = cur.fetchone()
            tier = (row[0] or "Free").title() if row else "Free"
            try:
                print(f"[tier lookup] email={user_email} tier={tier} db={db_path}")
            except Exception:
                pass
            return tier
        finally:
            conn.close()
    except Exception:
        return "Free"


def page_shell(body_html: str, title: str, user_email: Optional[str]) -> str:
    """
    Shared shell for all pages.
    user_email:
      - None if anonymous
      - "someone@company.com" if logged in
    """

    nav_links = _nav_links_html(user_email)
    user_tier = _get_user_tier(user_email)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
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
            {nav_links}
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
            <span class="top-label">Tier:</span> <strong>{user_tier}</strong>
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
                    <span class="avatar-circle">{(user_email or 'U')[:2].upper()}</span>
                </span>
                <span class="top-caret" aria-hidden="true">▾</span>
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
        {body_html}
        </main>
    </div>
</div>
<button class="sidebar-toggle" id="sidebar-toggle" aria-label="Toggle sidebar"><<</button>

<div id="notif-overlay" aria-hidden="true"></div>
<aside id="notif-drawer" aria-hidden="true">
  <header>
    <div>
      <div class="notif-title">Notifications</div>
      <div class="notif-sub">Inbox • Last 14 days</div>
    </div>
    <button class="icon-btn" id="notif-close" type="button" aria-label="Close notifications">×</button>
  </header>
  <div class="notif-list" id="notif-list">
    <div class="notif-item unread">
      <div class="notif-line">
        <span class="notif-pill">New</span>
        <span class="notif-time">Just now</span>
      </div>
      <div class="notif-body">New opportunity posted matching your keywords.</div>
      <button class="notif-link" type="button">View</button>
    </div>
    <div class="notif-item">
      <div class="notif-line">
        <span class="notif-pill muted">Update</span>
        <span class="notif-time">2h ago</span>
      </div>
      <div class="notif-body">Team comment added on “Water Treatment Plant RFP”.</div>
      <button class="notif-link" type="button">Open thread</button>
    </div>
  </div>
</aside>

<script>
document.addEventListener("DOMContentLoaded", function () {{
    const revealEls = Array.prototype.slice.call(document.querySelectorAll(".reveal"));

    if ("IntersectionObserver" in window) {{
        const obs = new IntersectionObserver((entries) => {{
            entries.forEach((entry) => {{
                if (entry.isIntersecting) {{
                    entry.target.classList.add("reveal-visible");
                    obs.unobserve(entry.target);
                }}
            }});
        }}, {{
            threshold: 0.15
        }});

        revealEls.forEach((el) => obs.observe(el));
    }} else {{
        revealEls.forEach((el) => el.classList.add("reveal-visible"));
    }}

}});
// notifications drawer
(function(){{
  const btn = document.getElementById('notif-btn');
  const drawer = document.getElementById('notif-drawer');
  const overlay = document.getElementById('notif-overlay');
  const closeBtn = document.getElementById('notif-close');
  if (!btn || !drawer || !overlay) return;
  const toggle = (open) => {{
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
  }};
  btn.addEventListener('click', function(){{ toggle(true); }});
  if (closeBtn) closeBtn.addEventListener('click', function(){{ toggle(false); }});
  overlay.addEventListener('click', function(){{ toggle(false); }});
}})();

// help dropdown
(function(){{
  const btn = document.getElementById('help-btn');
  const menu = document.getElementById('help-menu');
  if (!btn || !menu) return;
  const toggle = (open) => {{
    menu.style.display = open ? 'block' : 'none';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }};
  btn.addEventListener('click', function(){{
    const isOpen = menu.style.display === 'block';
    toggle(!isOpen);
  }});
  document.addEventListener('click', function(e){{
    if (!btn.contains(e.target) && !menu.contains(e.target)) toggle(false);
  }});
}})();


// avatar dropdown
(function(){{
  const btn = document.getElementById('avatar-btn');
  const menu = document.getElementById('avatar-menu');
  if (!btn || !menu) return;
  const toggle = (open) => {{
    menu.style.display = open ? 'block' : 'none';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }};
  btn.addEventListener('click', function(){{
    const isOpen = menu.style.display === 'block';
    toggle(!isOpen);
  }});
  document.addEventListener('click', function(e){{
    if (!btn.contains(e.target) && !menu.contains(e.target)) toggle(false);
  }});
}})();


// sidebar toggle
(function(){{
  const btn = document.getElementById('sidebar-toggle');
  if (!btn) return;
  btn.addEventListener('click', function(){{
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    btn.textContent = collapsed ? '>>' : '<<';
  }});
}})();

</script>


</body>
</html>

    """
