# app/routers/auth_web.py
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from typing import Optional
import json

from app.core.db import AsyncSessionLocal
from app.security import hash_password, verify_password
from app.auth.session import create_session_token, get_current_user_email, SESSION_COOKIE_NAME
from app.core.settings import settings

from app.api._layout import page_shell

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
    body_html = f"""
    <section class="card">
      <h2 class="section-heading">Create your account</h2>
      <p class="subtext">Start a free account to track bids and get alerts.</p>

      <form method="POST" action="/signup">
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
        <div class="form-actions">
          <label style="font-size:13px; color:#374151;"><input type="checkbox" name="remember"> Keep me signed in</label>
          <button class="button-primary" type="submit">Create account</button>
        </div>
        <div class="help-text">Already have an account? <a href="/login?next={next}">Sign in</a>.</div>
      </form>
    </section>
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
    return HTMLResponse(page_shell(body_html, title="Sign up • Muni Alerts", user_email=user_email))


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    remember: bool = Form(False),
):
    email_clean = email.strip().lower()
    pw_hash = hash_password(password)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at)
                VALUES (:email, :pw, 'daily', '[]', 1, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                  password_hash = excluded.password_hash,
                  is_active = 1
                """
            ),
            {"email": email_clean, "pw": pw_hash},
        )
        await session.commit()

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


# --- login/logout ----------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/"):
    # Do NOT redirect from here; show the form to avoid loops.
    user_email = get_current_user_email(request)
    body_html = f"""
    <section class="card">
      <h2 class="section-heading">Sign in</h2>
      <p class="subtext">Access your dashboard and alert settings.</p>

      <form method="POST" action="/login">
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
      </form>
    </section>
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
    return HTMLResponse(page_shell(body_html, title="Login • Muni Alerts", user_email=user_email))


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
                title="My Account • Muni Alerts",
                user_email=None,
            )
        )
    return HTMLResponse(
        page_shell(
            f"""
      <section class="card"><h2 class="section-heading">My Account</h2>
      <p class="subtext">Signed in as <b>{user_email}</b>.</p>
      <a class="button-primary" href="/logout">Sign out</a></section>
            """,
            title="My Account • Muni Alerts",
            user_email=user_email,
        )
    )
