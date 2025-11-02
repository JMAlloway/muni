# app/routers/auth_web.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from typing import List, Optional
import json

from app.db import AsyncSessionLocal
from app.security import hash_password, verify_password
from app.session import (
    create_session_token,
    get_current_user_email,
    SESSION_COOKIE_NAME,
)
from app.routers._layout import page_shell

router = APIRouter(tags=["auth"])


# -------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------

async def _load_user_by_email(email: str):
    """
    Backward-compatible load: only grab columns we KNOW exist.
    Do NOT assume created_at/updated_at exist in SQLite.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("""
                SELECT email,
                       password_hash,
                       digest_frequency,
                       agency_filter,
                       is_active
                FROM users
                WHERE email = :email
                LIMIT 1
            """),
            {"email": email.lower().strip()},
        )
        row = res.fetchone()

    if not row:
        return None

    (
        db_email,
        db_pw_hash,
        digest_frequency,
        agency_filter,
        is_active,
    ) = row

    return (
        db_email,
        db_pw_hash,
        digest_frequency,
        agency_filter,
        is_active,
    )


def _account_settings_card(
    db_email: str,
    digest_frequency: str,
    current_agencies: List[str],
    known_agencies: List[str],
    success_msg: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> str:
    """
    Render the account settings UI (no created_at/updated_at footer).
    """

    agency_boxes = []
    for ag in known_agencies:
        checked = "checked" if ag in current_agencies else ""
        agency_boxes.append(
            f"<label class='agency-choice'>"
            f"<input type='checkbox' name='agency' value='{ag}' {checked}/>"
            f"{ag}"
            "</label>"
        )

    def sel(val: str) -> str:
        return "selected" if digest_frequency == val else ""

    banner_html = ""
    if success_msg:
        banner_html = f"""
        <div class="alert-banner success" style="margin-bottom:16px;">
            <div class="alert-title">Saved ✔</div>
            <div class="alert-desc">{success_msg}</div>
        </div>
        """
    elif error_msg:
        banner_html = f"""
        <div class="alert-banner error" style="margin-bottom:16px;">
            <div class="alert-title">Please review</div>
            <div class="alert-desc">{error_msg}</div>
        </div>
        """

    human_freq = {
        "daily": "Daily (changes in last 24h)",
        "weekly": "Weekly (last 7 days)",
        "none": "Paused (no email right now)",
    }.get(digest_frequency, "Weekly (last 7 days)")

    agencies_label = (
        ", ".join(current_agencies)
        if current_agencies
        else "All agencies we track"
    )

    return f"""
    <section class="card">
        <h2 class="section-heading">My Alert Settings</h2>
        <p class="subtext">
            Signed in as <b>{db_email}</b>.
            <a href="/logout" class="cta-link" style="margin-left:8px;">Sign out</a>
        </p>

        {banner_html}

        <div class="mini-head">Current status</div>
        <div class="mini-desc" style="margin-bottom:16px;">
            <div><b>Email cadence:</b> {human_freq}</div>
            <div><b>Agencies watched:</b> {agencies_label}</div>
        </div>

        <form method="POST" action="/account">
            <div class="form-row">
                <div class="form-col">
                    <label class="label-small">Email frequency</label>
                    <select name="frequency" required>
                        <option value="daily" {sel("daily")}>Daily (last 24h)</option>
                        <option value="weekly" {sel("weekly")}>Weekly (last 7 days)</option>
                        <option value="none" {sel("none")}>Pause all emails</option>
                    </select>
                    <div class="muted" style="margin-top:4px;">
                        Change this any time. "Pause all emails" = you stay in the system,
                        but we won't send you digests.
                    </div>
                </div>

                <div class="form-col">
                    <label class="label-small">Agencies I care about</label>
                    <div class="agency-grid">
                        {''.join(agency_boxes)}
                    </div>
                    <div class="muted" style="margin-top:4px;">
                        Leave none selected = send everything.
                    </div>
                </div>
            </div>

            <button class="button-primary" type="submit">Save settings</button>
        </form>
    </section>

    <section class="card">
        <div class="mini-head">How alerts work</div>
        <div class="mini-desc">
            Daily emails include only opportunities created or updated in the last 24 hours.
            Weekly emails include the past 7 days.
            Paused means we don't email you for now.
        </div>
        <div class="muted" style="margin-top:12px;font-size:12px;line-height:1.4;">
            You can also fine-tune keywords and buyers under
            <a class="cta-link" href="/onboarding">Preferences</a>.
        </div>
    </section>

    <style>
        .alert-banner {{
            border-radius:8px;
            padding:12px 16px;
            font-size:13px;
            line-height:1.4;
        }}
        .alert-banner.success {{
            background:#ECFDF5;
            border:1px solid #A7F3D0;
            color:#065F46;
        }}
        .alert-banner.error {{
            background:#FEF2F2;
            border:1px solid #FECACA;
            color:#B91C1C;
        }}
        .alert-title {{
            font-weight:600;
            margin-bottom:2px;
        }}
        .alert-desc {{
            font-weight:400;
        }}
    </style>
    """


async def _render_account_page(
    request: Request,
    success_msg: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> HTMLResponse:
    """
    Shared renderer so GET and POST both reuse the same display.
    """
    email = get_current_user_email(request)
    if not email:
        # No session cookie / expired session
        body_html = """
        <section class="card">
            <h2 class="section-heading">You're signed out</h2>
            <p class="subtext">
                Please sign in to manage alerts.
            </p>
            <a class="button-primary" href="/login">Sign in →</a>
            <div class="muted" style="margin-top:12px;">
                Don’t have an account?
                <a class="cta-link" href="/signup">Create one</a>.
            </div>
        </section>
        """
        return HTMLResponse(
            page_shell(body_html, title="My Account – Muni Alerts", user_email=None)
        )

    row = await _load_user_by_email(email)
    if not row:
        # Session cookie exists but user row is gone
        body_html = f"""
        <section class="card">
            <h2 class="section-heading">Account not found</h2>
            <p class="subtext">
                We couldn't find an active profile for <b>{email}</b>.
            </p>
            <a class="button-primary" href="/signup">Create account →</a>
            <div class="muted" style="margin-top:12px;">
                If you think this is a mistake, sign out and log in again.
            </div>
            <div style="margin-top:12px;">
                <a class="cta-link" href="/logout">Sign out</a>
            </div>
        </section>
        """
        return HTMLResponse(
            page_shell(body_html, title="My Account – Muni Alerts", user_email=email),
            status_code=404,
        )

    (
        db_email,
        _pw_hash,
        digest_frequency,
        agency_filter_json,
        is_active,
    ) = row

    if not is_active:
        body_html = f"""
        <section class="card">
            <h2 class="section-heading">Account inactive</h2>
            <p class="subtext">
                Your alerts are currently disabled for <b>{db_email}</b>.
            </p>
            <div class="mini-desc" style="margin-bottom:16px;">
                Reactivate below to start receiving opportunities again.
            </div>
            <a class="button-primary" href="/login">Reactivate →</a>
            <div class="muted" style="margin-top:12px;">
                Or <a class="cta-link" href="/logout">sign out</a>.
            </div>
        </section>
        """
        return HTMLResponse(
            page_shell(body_html, title="My Account – Muni Alerts", user_email=email),
            status_code=403,
        )

    # agencies array from DB
    try:
        current_agencies = json.loads(agency_filter_json or "[]")
        if not isinstance(current_agencies, list):
            current_agencies = []
    except Exception:
        current_agencies = []

    # same list you were already showing
    known_agencies = [
        "City of Columbus",
        "City of Grove City",
        "City of Gahanna",
    ]

    body_html = _account_settings_card(
        db_email=db_email,
        digest_frequency=digest_frequency,
        current_agencies=current_agencies,
        known_agencies=known_agencies,
        success_msg=success_msg,
        error_msg=error_msg,
    )

    return HTMLResponse(
        page_shell(body_html, title="My Account – Muni Alerts", user_email=email)
    )


# -------------------------------------------------------------------
# public routes (signup / login / logout)
# -------------------------------------------------------------------

@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    user_email = get_current_user_email(request)

    known_agencies = [
        "City of Columbus",
        "Delaware County",
        "Franklin County",
        "Union County",
        "Licking County",
        "Madison County",
    ]

    agencies_html = []
    for ag in known_agencies:
        agencies_html.append(
            f"<label class='agency-choice'>"
            f"<input type='checkbox' name='agency' value='{ag}' />"
            f"{ag}"
            "</label>"
        )

    body_html = f"""
    <section class="card">
        <h2 class="section-heading">Create your account</h2>
        <p class="subtext">
            We'll email you new & updated opportunities either daily or weekly.
            You can change this anytime.
        </p>

        <form method="POST" action="/signup">
            <div class="form-row">
                <div class="form-col">
                    <label class="label-small">Work email</label>
                    <input type="text" name="email" placeholder="you@company.com" required />
                </div>

                <div class="form-col">
                    <label class="label-small">Password</label>
                    <input type="text" name="password" placeholder="Choose a password" required />
                    <div class="muted" style="margin-top:4px;">
                        We'll keep this secure.
                    </div>
                </div>
            </div>

            <div class="form-row">
                <div class="form-col">
                    <label class="label-small">How often?</label>
                    <select name="frequency" required>
                        <option value="daily">Daily (last 24h)</option>
                        <option value="weekly">Weekly (last 7 days)</option>
                        <option value="none">No email yet</option>
                    </select>
                </div>
                <div class="form-col">
                    <label class="label-small">Agencies to watch</label>
                    <div class="agency-grid">
                        {''.join(agencies_html)}
                    </div>
                    <div class="muted" style="margin-top:4px;">
                        Leave blank for “all”.
                    </div>
                </div>
            </div>

            <button class="button-primary" type="submit">Create account →</button>
        </form>

        <div class="muted" style="margin-top:16px;">
            Already have an account? <a href="/login" class="cta-link">Sign in</a>
        </div>
    </section>
    """
    return HTMLResponse(
        page_shell(body_html, title="Sign up – Muni Alerts", user_email=user_email)
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    frequency: str = Form(...),
    agency: List[str] = Form([]),
):
    email_clean = email.strip().lower()
    freq_clean = frequency.strip().lower()
    if freq_clean not in ("daily", "weekly", "none"):
        freq_clean = "daily"

    pw_hash = hash_password(password)
    agencies_json = json.dumps(agency)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at)
                VALUES (:email, :pw, :freq, :agencies, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    password_hash = COALESCE(users.password_hash, excluded.password_hash),
                    digest_frequency = excluded.digest_frequency,
                    agency_filter = excluded.agency_filter,
                    is_active = 1
            """),
            {
                "email": email_clean,
                "pw": pw_hash,
                "freq": freq_clean,
                "agencies": agencies_json,
            },
        )
        await session.commit()

    token = create_session_token(email_clean)
    resp = RedirectResponse(url="/account", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return resp


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    user_email = get_current_user_email(request)

    body_html = """
    <section class="card">
        <h2 class="section-heading">Sign in</h2>
        <p class="subtext">
            Access your alert settings.
        </p>

        <form method="POST" action="/login">
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

        <div class="muted" style="margin-top:16px;">
            Need an account? <a href="/signup" class="cta-link">Create one</a>
        </div>
    </section>
    """
    return HTMLResponse(
        page_shell(body_html, title="Login – Muni Alerts", user_email=user_email)
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    email: str = Form(...),
    password: str = Form(...),
):
    email_clean = email.strip().lower()
    row = await _load_user_by_email(email_clean)

    if not row:
        body_html = """
        <section class="card">
            <h2 class="section-heading">Sign in</h2>
            <p class="subtext" style="color:#dc2626;">Invalid email or password.</p>
            <a class="button-primary" href="/login">Try again →</a>
        </section>
        """
        return HTMLResponse(
            page_shell(body_html, title="Login failed", user_email=None),
            status_code=401,
        )

    (
        db_email,
        db_pw_hash,
        _freq,
        _agency_filter,
        is_active,
    ) = row

    if (not is_active) or (not verify_password(password, db_pw_hash)):
        body_html = """
        <section class="card">
            <h2 class="section-heading">Sign in</h2>
            <p class="subtext" style="color:#dc2626;">Invalid email or password.</p>
            <a class="button-primary" href="/login">Try again →</a>
        </section>
        """
        return HTMLResponse(
            page_shell(body_html, title="Login failed", user_email=None),
            status_code=401,
        )

    token = create_session_token(email_clean)
    resp = RedirectResponse(url="/account", status_code=303)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return resp


@router.get("/logout", response_class=HTMLResponse)
async def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


# -------------------------------------------------------------------
# account routes (inline success banner)
# -------------------------------------------------------------------

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    return await _render_account_page(request)


@router.post("/account", response_class=HTMLResponse)
async def account_update(
    request: Request,
    frequency: str = Form(...),
    agency: List[str] = Form([]),
):
    email = get_current_user_email(request)
    if not email:
        # Session gone; fall back to signed-out card
        return await _render_account_page(request)

    freq_clean = (frequency or "").strip().lower()
    if freq_clean not in ("daily", "weekly", "none"):
        freq_clean = "daily"

    agencies_clean = [a.strip() for a in agency if a.strip()]
    agencies_json = json.dumps(agencies_clean)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE users
                SET digest_frequency = :freq,
                    agency_filter = :agencies
                WHERE email = :email
            """),
            {
                "freq": freq_clean,
                "agencies": agencies_json,
                "email": email.lower().strip(),
            },
        )
        await session.commit()

    # Render page again with success banner
    return await _render_account_page(
        request,
        success_msg="Your alert settings were updated.",
        error_msg=None,
    )
