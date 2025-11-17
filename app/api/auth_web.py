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
    body_html = f"""
    <section class="card">
      <h2 class="section-heading">Create your account</h2>
      <p class="subtext">Start a free account to track bids, get alerts, and save documents.</p>

      <form method="POST" action="/signup">\n        <input type="hidden" name="csrf_token" id="csrf_signup" value="{csrf_cookie}">
        <input type="hidden" name="next" value="{next}">
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
        <div class="form-actions">
          <label style="font-size:13px; color:#374151;"><input type="checkbox" name="remember"> Keep me signed in</label>
          <button class="button-primary" type="submit">Create account</button>
        </div>
        <div class="help-text">Already have an account? <a href="/login?next={next}">Sign in</a>.</div>
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
    resp = HTMLResponse(page_shell(body_html, title="Sign up  Muni Alerts", user_email=user_email))
    resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax")
    return resp


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    remember: bool = Form(False),
    primary_interest: str = Form(DEFAULT_INTEREST_KEY),
):
    email_clean = email.strip().lower()
    pw_hash = hash_password(password)
    valid_interests = {opt["key"] for opt in list_interest_options()}
    interest_choice = (primary_interest or DEFAULT_INTEREST_KEY).strip().lower()
    if interest_choice not in valid_interests:
        interest_choice = DEFAULT_INTEREST_KEY

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
    redirect_to = "/welcome"
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
    resp = HTMLResponse(page_shell(body_html, title="Sign up  Muni Alerts", user_email=user_email)); resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax"); return resp


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
                title="My Account · Muni Alerts",
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
</div>
    """
    body = body.format(user_email=user_email)
    return HTMLResponse(
        page_shell(
            body,
            title="My Account · Muni Alerts",
            user_email=user_email,
        )
    )

