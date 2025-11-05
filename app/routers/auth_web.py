# app/routers/auth_web.py
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from typing import List
import json

from app.db import AsyncSessionLocal
from app.security import hash_password, verify_password
from app.session import create_session_token, get_current_user_email, SESSION_COOKIE_NAME
from app.settings import settings

from app.routers._layout import page_shell

router = APIRouter(tags=["auth"])

# --- helpers ---------------------------------------------------------

async def _load_user_by_email(email: str):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("""
                SELECT email, password_hash, digest_frequency, agency_filter, is_active
                FROM users
                WHERE email = :email
                LIMIT 1
            """),
            {"email": email.lower().strip()},
        )
        return res.fetchone()

# --- signup ----------------------------------------------------------

@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    user_email = get_current_user_email(request)
    body_html = f"""
    <section class="card">
      <h2 class="section-heading">Create your account</h2>
      <form method="POST" action="/signup">
        <div class="form-row">
          <div class="form-col">
            <label class="label-small">Email</label>
            <input type="text" name="email" required />
          </div>
          <div class="form-col">
            <label class="label-small">Password</label>
            <input type="text" name="password" required />
          </div>
        </div>
        <button class="button-primary" type="submit">Create →</button>
      </form>
    </section>
    """
    return HTMLResponse(page_shell(body_html, title="Sign up – Muni Alerts", user_email=user_email))

@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(email: str = Form(...), password: str = Form(...)):
    email_clean = email.strip().lower()
    pw_hash = hash_password(password)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at)
                VALUES (:email, :pw, 'daily', '[]', 1, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                  password_hash = excluded.password_hash,
                  is_active = 1
            """),
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
        max_age=60 * 60 * 2  # 2 hours
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
            <input type="text" name="email" placeholder="you@company.com" required />
          </div>
          <div class="form-col">
            <label class="label-small">Password</label>
            <input type="text" name="password" placeholder="Your password" required />
          </div>
        </div>
        <button class="button-primary" type="submit">Sign in →</button>
      </form>
    </section>
    """
    return HTMLResponse(page_shell(body_html, title="Login – Muni Alerts", user_email=user_email))

@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    email_clean = email.strip().lower()
    print(f"[DEBUG login] start email={email_clean!r} next={next!r}")

    row = await _load_user_by_email(email_clean)
    if not row:
        print("[DEBUG login] no such user")
        return HTMLResponse(page_shell("""
          <section class="card"><h2 class="section-heading">Sign in failed</h2>
          <p class="subtext" style="color:#dc2626;">Invalid email or password.</p>
          <a class="button-primary" href="/login">Try again →</a></section>
        """, title="Login failed", user_email=None), status_code=401)

    db_email, db_pw_hash, *_rest, is_active = row
    if not is_active:
        print("[DEBUG login] inactive account", db_email)
        return HTMLResponse(page_shell("""
          <section class="card"><h2 class="section-heading">Account inactive</h2></section>
        """, title="Inactive", user_email=None), status_code=403)

    if not verify_password(password, db_pw_hash):
        print("[DEBUG login] bad password for", db_email)
        return HTMLResponse(page_shell("""
          <section class="card"><h2 class="section-heading">Sign in failed</h2>
          <p class="subtext" style="color:#dc2626;">Invalid email or password.</p>
          <a class="button-primary" href="/login">Try again →</a></section>
        """, title="Login failed", user_email=None), status_code=401)

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
        max_age=60 * 60 * 2  # 2 hours
    )

    return resp


@router.get("/logout", response_class=HTMLResponse)
async def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    print("[DEBUG logout] cleared session")
    return resp

# --- minimal /account (optional) ------------------------------------

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        # just show a gentle sign-in prompt; do NOT redirect here
        return HTMLResponse(page_shell("""
          <section class="card"><h2 class="section-heading">You’re signed out</h2>
          <a class="button-primary" href="/login">Sign in →</a></section>
        """, title="My Account – Muni Alerts", user_email=None))
    return HTMLResponse(page_shell(f"""
      <section class="card"><h2 class="section-heading">My Account</h2>
      <p class="subtext">Signed in as <b>{user_email}</b>.</p>
      <a class="button-primary" href="/logout">Sign out</a></section>
    """, title="My Account – Muni Alerts", user_email=user_email))
