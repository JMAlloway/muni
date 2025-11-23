# app/routers/auth_web.py
from fastapi import APIRouter, Request, Form
import secrets
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from typing import Optional
import json

from app.core.db import AsyncSessionLocal
from app.security import hash_password, verify_password
from app.auth.session import create_session_token, get_current_user_email, SESSION_COOKIE_NAME
from app.core.settings import settings

from app.api._layout import page_shell
from app.onboarding.interests import DEFAULT_INTEREST_KEY, list_interest_options
from app.services import record_milestone, set_primary_interest

router = APIRouter(tags=["auth"])

# --- helpers ---------------------------------------------------------

async def _load_user_by_email(email: str):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text(
                """
                SELECT email, password_hash, digest_frequency, agency_filter, is_active
                FROM users
                WHERE email = :email
                LIMIT 1
                """
            ),
            {"email": email.lower().strip()},
        )
        return res.fetchone()


# --- signup ----------------------------------------------------------

@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, next: str = "/"):
    user_email = get_current_user_email(request)
    csrf_cookie = request.cookies.get("csrftoken") or secrets.token_urlsafe(32)
    interest_opts = list_interest_options()
    options_html = "".join(
        f"<option value='{opt['key']}' {'selected' if opt['key'] == DEFAULT_INTEREST_KEY else ''}>{opt['label']}</option>"
        for opt in interest_opts
    )
    plan_cards = [
        {"key": "free", "name": "Free", "price": "$0", "perk": "Try the core workflow", "best": False},
        {"key": "starter", "name": "Starter", "price": "$29/mo", "perk": "Real-time alerts + unlimited bids", "best": True},
        {"key": "professional", "name": "Pro", "price": "$99/mo", "perk": "Team-ready + AI matching", "best": False},
        {"key": "enterprise", "name": "Enterprise", "price": "$299/mo", "perk": "Unlimited seats + API access", "best": False},
    ]
    plan_html = "".join(
        [
            f"""
            <label class="plan-tile {'plan-best' if p['best'] else ''}" data-plan="{p['key']}">
              <input type="radio" name="plan_choice" value="{p['key']}" {'checked' if p['key']=='free' else ''}>
              <div class="plan-top">
                <div class="plan-name">{p['name']}</div>
                <div class="plan-price">{p['price']}</div>
              </div>
              <div class="plan-perk">{p['perk']}</div>
              <div class="plan-cta">{'Most popular' if p['best'] else 'Select'}</div>
            </label>
            """
            for p in plan_cards
        ]
    )
    body_html = f"""
    <section class="card">
      <h2 class="section-heading">Create your account</h2>
      <p class="subtext">Start in seconds. Pick a plan now—paid plans head straight to secure Stripe checkout.</p>

      <form method="POST" action="/signup">\n        <input type="hidden" name="csrf_token" id="csrf_signup" value="{csrf_cookie}">
        <input type="hidden" name="next" value="{next}">
        <input type="hidden" name="plan" id="plan-hidden" value="free">
        <div class="form-row">
          <div class="form-col">
            <label class="label-small">Email</label>
            <input type="email" name="email" placeholder="you@company.com" required />
          </div>
          <div class="form-col">
            <label class="label-small">Password</label>
            <div class="input-with-toggle">
              <input id="signup-password" type="password" name="password" placeholder="Create a strong password" required />
              <button type="button" class="pw-toggle" aria-controls="signup-password" aria-label="Show password">Show</button>
            </div>
            <div class="help-text">Minimum 8 characters recommended.</div>
          </div>
        </div>
        <div class="form-row">
          <div class="form-col">
            <label class="label-small">Primary interest</label>
            <select name="primary_interest">{options_html}</select>
            <div class="help-text">We use this to auto-tailor your welcome dashboard.</div>
          </div>
        </div>
        <div class="form-row plan-chooser">
          <div class="plan-chooser-head">
            <div>
              <div class="label-small">Pick your starting plan</div>
              <div class="help-text">Upgrade sends you to Stripe after signup; Free goes straight to your dashboard.</div>
            </div>
            <div class="plan-chooser-note">Change anytime</div>
          </div>
          <div class="plan-tiles">{plan_html}</div>
        </div>
        <div class="form-actions">
          <label style="font-size:13px; color:#374151;"><input type="checkbox" name="remember"> Keep me signed in</label>
          <button class="button-primary" type="submit">Create account & continue</button>
        </div>
        <div class="help-text">Already have an account? <a href="/login?next={next}">Sign in</a>.</div>
      </form>\\n    </section>
    <style>
      .plan-chooser {{ display:grid; gap:12px; }}
      .plan-chooser-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
      .plan-chooser-note {{ font-size:12px; color:#0f172a; background:#e0f2fe; padding:6px 10px; border-radius:12px; }}
      .plan-tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px; }}
      .plan-tile {{ border:1px solid #e5e7eb; border-radius:12px; padding:12px; display:grid; gap:6px; cursor:pointer; transition:all 0.15s ease; background:#fff; position:relative; }}
      .plan-tile:hover {{ box-shadow:0 8px 20px rgba(15,23,42,0.08); transform:translateY(-1px); }}
      .plan-tile input[type="radio"] {{ position:absolute; opacity:0; inset:0; }}
      .plan-tile .plan-top {{ display:flex; justify-content:space-between; align-items:center; font-weight:600; }}
      .plan-tile .plan-price {{ color:#2563eb; }}
      .plan-tile .plan-perk {{ color:#334155; font-size:13px; }}
      .plan-tile .plan-cta {{ font-size:12px; color:#0f172a; opacity:0.8; }}
      .plan-tile.plan-best {{ border-color: rgba(37,99,235,0.5); box-shadow:0 0 0 2px rgba(37,99,235,0.15); }}
      .plan-tile.selected {{ border-color:#2563eb; box-shadow:0 0 0 2px rgba(37,99,235,0.2); }}
    </style>
    <script>
      (function() {{
        var btn=document.querySelector('.pw-toggle');
        if(btn) {{
          btn.addEventListener('click',function() {{
            var id=this.getAttribute('aria-controls');
            var input=id?document.getElementById(id):null;
            if(!input) return;
            if(input.type==='password') {{ input.type='text'; this.textContent='Hide'; this.setAttribute('aria-label','Hide password'); }}
            else {{ input.type='password'; this.textContent='Show'; this.setAttribute('aria-label','Show password'); }}
          }});
        }}
        var tiles = Array.prototype.slice.call(document.querySelectorAll('.plan-tile'));
        tiles.forEach(function(tile){{
          tile.addEventListener('click', function(ev){{
            var radio = tile.querySelector('input[type=\"radio\"]');
            if(!radio) return;
            radio.checked = true;
            tiles.forEach(function(t){{ t.classList.toggle('selected', t===tile); }});
          }});
        }});
      }})();
    </script>
    """
    resp = HTMLResponse(page_shell(body_html, title="Sign up - EasyRFP", user_email=user_email))
    resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax")
    return resp


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    remember: bool = Form(False),
    primary_interest: str = Form(DEFAULT_INTEREST_KEY),
    plan: str = Form("free"),
):
    email_clean = email.strip().lower()
    pw_hash = hash_password(password)
    valid_interests = {opt["key"] for opt in list_interest_options()}
    interest_choice = (primary_interest or DEFAULT_INTEREST_KEY).strip().lower()
    if interest_choice not in valid_interests:
        interest_choice = DEFAULT_INTEREST_KEY
    allowed_plans = {"free", "starter", "professional", "enterprise"}
    plan_choice = (plan or "free").strip().lower()
    if plan_choice not in allowed_plans:
        plan_choice = "free"

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at, primary_interest, onboarding_step, onboarding_completed)
                VALUES (:email, :pw, 'daily', '[]', 1, CURRENT_TIMESTAMP, :interest, 'signup', 0)
                ON CONFLICT(email) DO UPDATE SET
                  password_hash = excluded.password_hash,
                  is_active = 1,
                  primary_interest = :interest,
                  onboarding_step = 'signup',
                  onboarding_completed = 0
                """
            ),
            {"email": email_clean, "pw": pw_hash, "interest": interest_choice},
        )
        await session.commit()

    await set_primary_interest(email_clean, interest_choice)
    await record_milestone(email_clean, "signup", {"source": "signup_form"})

    token = create_session_token(email_clean)
    redirect_to = "/welcome" if plan_choice == "free" else f"/billing/checkout?plan={plan_choice}"
    resp = RedirectResponse(url=redirect_to, status_code=303)

    is_prod = settings.ENV.lower() == "production"
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        path="/",
        max_age=(60 * 60 * 24 * 30) if remember else (60 * 60 * 2),
    )

    return resp


# --- login/logout ----------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/"):
    # Do NOT redirect from here; show the form to avoid loops.
    user_email = get_current_user_email(request)
    csrf_cookie = request.cookies.get("csrftoken") or secrets.token_urlsafe(32)
    body_html = f"""
    <section class="card">
      <h2 class="section-heading">Sign in</h2>
      <p class="subtext">Access your dashboard and alert settings.</p>

      <form method="POST" action="/login">\n        <input type="hidden" name="csrf_token" id="csrf_login" value="{csrf_cookie}">
        <input type="hidden" name="next" value="{next}">
        <div class="form-row">
          <div class="form-col">
            <label class="label-small">Email</label>
            <input type="email" name="email" placeholder="you@company.com" required />
          </div>
          <div class="form-col">
            <label class="label-small">Password</label>
            <div class="input-with-toggle">
              <input id="login-password" type="password" name="password" placeholder="Your password" required />
              <button type="button" class="pw-toggle" aria-controls="login-password" aria-label="Show password">Show</button>
            </div>
          </div>
        </div>
        <div class="form-actions">
          <label style="font-size:13px; color:#374151;"><input type="checkbox" name="remember"> Keep me signed in</label>
          <button class="button-primary" type="submit">Sign in</button>
        </div>
        <div class="help-text">No account yet? <a href="/signup?next={next}">Create one</a>.</div>
      </form>\\n    </section>
    <script>
      (function() {{
        var btn=document.querySelector('.pw-toggle');
        if(!btn) return;
        btn.addEventListener('click',function() {{
          var id=this.getAttribute('aria-controls');
          var input=id?document.getElementById(id):null;
          if(!input) return;
          if(input.type==='password') {{ input.type='text'; this.textContent='Hide'; this.setAttribute('aria-label','Hide password'); }}
          else {{ input.type='password'; this.textContent='Show'; this.setAttribute('aria-label','Show password'); }}
        }});
      }})();
    </script>
    """
    resp = HTMLResponse(page_shell(body_html, title="Sign up - EasyRFP", user_email=user_email)); resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax"); return resp


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    remember: bool = Form(False),
):
    email_clean = email.strip().lower()
    row = await _load_user_by_email(email_clean)
    if not row:
        return HTMLResponse(
            page_shell(
                """
          <section class="card"><h2 class="section-heading">Sign in failed</h2>
          <p class="subtext" style="color:#dc2626;">Invalid email or password.</p>
          <a class="button-primary" href="/login">Try again</a></section>
                """,
                title="Login failed",
                user_email=None,
            ),
            status_code=401,
        )

    db_email, db_pw_hash, *_rest, is_active = row
    if not is_active:
        return HTMLResponse(
            page_shell(
                """
          <section class="card"><h2 class="section-heading">Account inactive</h2></section>
                """,
                title="Inactive",
                user_email=None,
            ),
            status_code=403,
        )

    if not verify_password(password, db_pw_hash):
        return HTMLResponse(
            page_shell(
                """
          <section class="card"><h2 class="section-heading">Sign in failed</h2>
          <p class="subtext" style="color:#dc2626;">Invalid email or password.</p>
          <a class="button-primary" href="/login">Try again</a></section>
                """,
                title="Login failed",
                user_email=None,
            ),
            status_code=401,
        )

    # Set cookie and redirect
    token = create_session_token(email_clean)
    redirect_to = next if (next and not next.startswith("/login")) else "/account"
    resp = RedirectResponse(url=redirect_to, status_code=303)

    is_prod = settings.ENV.lower() == "production"
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        path="/",
        max_age=(60 * 60 * 24 * 30) if remember else (60 * 60 * 2),
    )

    return resp


@router.get("/logout", response_class=HTMLResponse)
async def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return resp


# --- minimal /account (optional) ------------------------------------

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        # gentle sign-in prompt; do NOT redirect here
        return HTMLResponse(
            page_shell(
                """
          <section class="card"><h2 class="section-heading">You're signed out</h2>
          <a class="button-primary" href="/login">Sign in</a></section>
                """,
                title="My Account - EasyRFP",
                user_email=None,
            )
        )

    body = """
<style>
._card-shell {{ border:1px solid #e2e8f0; border-radius:18px; padding:18px; background:#fff; box-shadow:0 10px 40px rgba(15,23,42,.08); }}
.account-hero {{ display:flex; justify-content:space-between; align-items:flex-start; gap:18px; }}
.account-hero .title {{ font-size:22px; font-weight:800; margin:0; letter-spacing:-0.01em; }}
.account-hero .subtext {{ margin:6px 0 0 0; color:#475569; }}
.pill {{ display:inline-flex; align-items:center; gap:6px; background:#eff6ff; color:#1d4ed8; border:1px solid #dbeafe; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
.account-subnav {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 10px 0; }}
.account-subnav a {{
  padding:10px 14px; border-radius:12px; border:1px solid #e2e8f0; background:#f8fafc;
  text-decoration:none; color:#0f172a; font-weight:600; font-size:14px; transition:all .15s ease;
}}
.account-subnav a:hover {{ transform:translateY(-1px); box-shadow:0 8px 20px rgba(15,23,42,.08); }}
.account-subnav a.primary {{ background:#2563eb; color:#fff; border-color:#2563eb; box-shadow:0 10px 28px rgba(37,99,235,.25); }}
.account-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px; }}
.account-card {{
  border:1px solid #e5e7eb; border-radius:16px; padding:16px;
  background:linear-gradient(180deg, #fff, #f8fafc);
  box-shadow:0 10px 28px rgba(15,23,42,.08);
  display:grid; gap:9px;
}}
.account-card h3 {{ margin:0; font-size:16px; font-weight:700; color:#0f172a; }}
.account-card p {{ margin:0; color:#475569; font-size:14px; line-height:1.55; }}
.account-card .actions {{ display:flex; gap:8px; flex-wrap:wrap; }}
.account-meta {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; color:#475569; font-size:13px; }}
.muted {{ color:#64748b; }}
</style>
<section class="card" style="border:0; box-shadow:none; padding:0;">
  <div class="account-hero">
    <div>
      <h2 class="title">My Account</h2>
      <p class="subtext">Signed in as <b>{user_email}</b></p>
      <div class="account-meta">
        <span class="pill">Active</span>
        <span>Alerts, tracker, and uploads included</span>
      </div>
    </div>
    <div><a class="button-primary" href="/logout">Sign out</a></div>
  </div>
  <div class="account-subnav">
    <a class="primary" href="/account">Overview</a>
    <a href="/onboarding">Preferences &amp; onboarding</a>
    <a href="/tracker/dashboard">Dashboard</a>
    <a href="/account/team">Team</a>
  </div>
</section>

<div class="account-grid">
  <div class="account-card">
    <h3>Profile</h3>
    <p>Manage your sign-in, contact email, and organization details.</p>
    <div class="actions">
      <a class="button-primary" href="/login?next=/account">Manage sign-in</a>
    </div>
  </div>
  <div class="account-card">
    <h3>Preferences &amp; onboarding</h3>
    <p>Tell us what you buy so alerts and the dashboard stay relevant.</p>
    <div class="actions">
      <a class="btn-secondary" href="/onboarding">Open preferences</a>
    </div>
  </div>
  <div class="account-card">
    <h3>Notifications</h3>
    <p>Control email digests and important updates.</p>
    <div class="actions">
      <a class="btn-secondary" href="/preferences">Notification settings</a>
    </div>
  </div>
  <div class="account-card">
    <h3>Tracker &amp; uploads</h3>
    <p>Jump to your bid dashboard to update status or upload files.</p>
    <div class="actions">
      <a class="btn-secondary" href="/tracker/dashboard">Go to dashboard</a>
    </div>
  </div>
  <div class="account-card">
    <h3>Team (Professional)</h3>
    <p>Invite up to 3 teammates to collaborate on bids and notes.</p>
    <div class="actions">
      <a class="btn-secondary" href="/account/team">Manage team</a>
    </div>
  </div>
</div>
    """
    body = body.format(user_email=user_email)
    return HTMLResponse(
        page_shell(
            body,
            title="My Account - EasyRFP",
            user_email=user_email,
        )
    )


@router.get("/account/team", response_class=HTMLResponse)
async def team_settings(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        return RedirectResponse("/login?next=/account/team", status_code=303)

    body = """
<style>
.team-shell {{
  display:grid; gap:12px;
}}
.team-card {{
  border:1px solid #e5e7eb;
  border-radius:16px;
  padding:16px;
  background:#fff;
  box-shadow:0 12px 30px rgba(15,23,42,.08);
}}
.team-card h3 {{ margin:0 0 6px 0; font-size:18px; font-weight:700; }}
.team-card p {{ margin:0 0 8px 0; color:#475569; }}
.muted {{ color:#64748b; font-size:13px; }}
.team-list {{ display:grid; gap:8px; padding:0; margin:0; list-style:none; }}
.team-list li {{
  border:1px solid #e5e7eb;
  border-radius:12px;
  padding:10px 12px;
  background:#f8fafc;
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:8px;
}}
.pill {{ display:inline-flex; align-items:center; gap:6px; background:#eff6ff; color:#1d4ed8; border:1px solid #dbeafe; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
.pill.pending {{ background:#fff7ed; color:#c2410c; border-color:#fed7aa; }}
.pill.active {{ background:#ecfdf3; color:#166534; border-color:#bbf7d0; }}
.form-row {{ display:flex; gap:8px; flex-wrap:wrap; }}
.form-row input {{ flex:1; min-width:220px; padding:9px 10px; border:1px solid #e5e7eb; border-radius:10px; }}
</style>

<section class="card team-shell">
  <div class="head-row" style="align-items:flex-start;">
    <div>
      <h2 class="section-heading">Team</h2>
      <div class="muted">Invite up to 3 people on Professional (owner counts as a seat).</div>
    </div>
    <div class="pill">Professional / Admin</div>
  </div>

  <div class="team-card">
    <h3>Invite teammates</h3>
    <p>Send up to 3 additional invites. Invites are limited by your plan (Professional: 4 seats incl. owner).</p>
    <div class="form-row">
      <input id="invite-email-1" type="email" placeholder="teammate1@example.com" />
      <input id="invite-email-2" type="email" placeholder="teammate2@example.com" />
      <input id="invite-email-3" type="email" placeholder="teammate3@example.com" />
      <button id="invite-btn" class="button-primary" type="button">Send invites</button>
    </div>
    <div id="invite-status" class="muted" style="margin-top:6px;"></div>
  </div>

  <div class="team-card">
    <h3>Members</h3>
    <p class="muted">Seats: <span id="seat-count">-</span> of 4 (Professional)</p>
    <ul id="team-list" class="team-list">
      <li class="muted">Loading team...</li>
    </ul>
    <div class="actions" style="margin-top:10px;">
      <button id="accept-btn" class="btn-secondary" type="button">Accept invite for this account</button>
      <span id="accept-status" class="muted"></span>
    </div>
  </div>
</section>

<script>
(function(){
  function getCSRF(){
    try { return (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||[])[1] || null; } catch(_) { return null; }
  }

  const listEl = document.getElementById("team-list");
  const statusEl = document.getElementById("invite-status");
  const seatEl = document.getElementById("seat-count");
  const btn = document.getElementById("invite-btn");
  const acceptBtn = document.getElementById("accept-btn");
    const acceptStatus = document.getElementById("accept-status");
    const currentUser = "__CURRENT_USER__".toLowerCase();

  function renderMembers(members){
    seatEl.textContent = members.length;
    if (!members.length){
      listEl.innerHTML = "<li class='muted'>No team members yet.</li>";
      return;
    }
    listEl.innerHTML = members.map(m => `
      <li>
        <div>
          <div><b>${m.user_email || m.invited_email}</b></div>
          <div class="muted">${m.user_id ? "Accepted" : "Pending invite"} · Role: ${m.role}</div>
        </div>
        <span class="pill ${m.user_id ? "active" : "pending"}">${m.user_id ? "Active" : "Pending"}</span>
      </li>
    `).join("");
  }

  function updateAcceptState(members){
    if (!acceptBtn) return;
    const pending = members.find(m => !m.user_id && (m.invited_email||"").toLowerCase() === currentUser);
    if (pending){
      acceptBtn.disabled = false;
      acceptStatus.textContent = "You have a pending invite for this account.";
    } else {
      acceptBtn.disabled = true;
      acceptStatus.textContent = "No pending invite for this account.";
    }
  }

  async function loadMembers(){
    listEl.innerHTML = "<li class='muted'>Loading...</li>";
    try{
      const res = await fetch("/api/team/members", { credentials:"include" });
      if (!res.ok) throw new Error("HTTP "+res.status);
      const data = await res.json();
      const members = data.members || [];
      renderMembers(members);
      updateAcceptState(members);
    }catch(err){
      listEl.innerHTML = "<li class='muted'>Could not load team.</li>";
    }
  }

  async function sendInvites(){
    statusEl.textContent = "";
    const emails = [document.getElementById("invite-email-1"), document.getElementById("invite-email-2"), document.getElementById("invite-email-3")]
      .map(i => i && i.value.trim()).filter(Boolean);
    if (!emails.length){ statusEl.textContent = "Enter at least one email."; return; }
    btn.disabled = true;
    for (const em of emails){
      try{
        const res = await fetch("/api/team/invite", {
          method:"POST",
          credentials:"include",
          headers:{ "Content-Type":"application/json", "X-CSRF-Token": getCSRF() || "" },
          body: JSON.stringify({ email: em })
        });
        if (!res.ok){
          statusEl.textContent = "Invite failed for "+em+" (code "+res.status+").";
        }
      }catch(_){
        statusEl.textContent = "Invite failed for "+em+".";
      }
    }
    btn.disabled = false;
    statusEl.textContent = "Invites sent (if seats available).";
    loadMembers();
  }

  btn.addEventListener("click", sendInvites);
  if (acceptBtn) {
    acceptBtn.addEventListener("click", async function(){
      acceptStatus.textContent = "";
      acceptBtn.disabled = true;
      try{
        const res = await fetch("/api/team/accept", { method:"POST", credentials:"include", headers:{ "X-CSRF-Token": getCSRF() || "" } });
        if (!res.ok) throw new Error("HTTP "+res.status);
        acceptStatus.textContent = "Invite accepted.";
        loadMembers();
      }catch(err){
        acceptStatus.textContent = "No pending invite or error accepting.";
      }finally{
        acceptBtn.disabled = false;
      }
    });
  }
    loadMembers();
})();
</script>
    """
    body = body.replace("__CURRENT_USER__", user_email or "")
    return HTMLResponse(page_shell(body, title="Team Settings - EasyRFP", user_email=user_email))


@router.get("/team/accept", response_class=HTMLResponse)
async def accept_invite_ui(request: Request):
    """
    Lightweight accept screen for invited users. Use after clicking an invite link.
    """
    user_email = get_current_user_email(request)
    if not user_email:
        return RedirectResponse("/login?next=/team/accept", status_code=303)

    body = """
    <section class="card" style="max-width:620px; margin:0 auto;">
      <h2 class="section-heading">Accept team invite</h2>
      <p class="subtext">Signed in as <b>{EMAIL}</b>. If this email matches the invitation, click below to join the team.</p>
      <div style="display:flex; gap:10px; align-items:center; margin-top:12px;">
        <button id="accept-btn" class="button-primary" type="button">Accept invite</button>
        <span id="accept-status" class="muted"></span>
      </div>
      <p class="muted" style="margin-top:12px;">If you were invited with a different email, sign out and sign back in with that address.</p>
    </section>
    <script>
    (function(){
      const btn = document.getElementById("accept-btn");
      const statusEl = document.getElementById("accept-status");
      btn.addEventListener("click", async function(){
        statusEl.textContent = "";
        btn.disabled = true;
        try{
          const res = await fetch("/api/team/accept", { method:"POST", credentials:"include" });
          if (!res.ok) throw new Error("HTTP "+res.status);
          statusEl.textContent = "Accepted. You can close this tab or go to your dashboard.";
        }catch(err){
          statusEl.textContent = "No pending invite for this account.";
        }finally{
          btn.disabled = false;
        }
      });
    })();
    </script>
    """
    body = body.replace("{EMAIL}", user_email or "")
    return HTMLResponse(page_shell(body, title="Accept Team Invite", user_email=user_email))

