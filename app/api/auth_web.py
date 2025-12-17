# app/routers/auth_web.py
from fastapi import APIRouter, Request, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
import secrets
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy import text
from typing import Optional, Any
import logging
import json
import datetime as dt
from pathlib import Path

from app.core.db import AsyncSessionLocal
from app.security import hash_password, verify_password
from app.auth.session import create_session_token, get_current_user_email, SESSION_COOKIE_NAME
from app.core.settings import settings
from app.api.team import _ensure_team_feature_access
from sqlalchemy.exc import SQLAlchemyError
from app.storage import store_profile_file, create_presigned_get, USE_S3

PROFILE_ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}
PROFILE_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PROFILE_MAX_MB = 25
FILE_FIELDS = {
    "ohio_certificate",
    "cert_upload",
    "capability_statement",
    "product_catalogs",
    "ref1_letter",
    "ref2_letter",
    "ref3_letter",
    "ref4_letter",
    "ref5_letter",
    "sub1_certificate",
    "sub2_certificate",
    "sub3_certificate",
    "sub4_certificate",
    "sub5_certificate",
    "insurance_certificate",
    "bonding_letter",
    "price_list_upload",
    "w9_upload",
    "business_license",
    "safety_sheets",
    "warranty_info",
    "previous_contracts",
    "org_chart",
    "digital_signature",
    "signature_image",
    # NEW FIELDS TO ADD:
    "financial_statements",      # Common in RFPs
    "debarment_certification",   # Federal requirement
    "labor_compliance_cert",     # Prevailing wage compliance
    "conflict_of_interest",      # Ethics certification
    "references_combined",       # Combined references document
}

from app.api._layout import auth_shell, page_shell
from app.onboarding.interests import DEFAULT_INTEREST_KEY, list_interest_options
from app.services import record_milestone, set_primary_interest

router = APIRouter(tags=["auth"])

# --- helpers ---------------------------------------------------------

def _valid_storage_key(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    if not val.strip():
        return False
    # Ignore stringified UploadFile objects or obvious placeholders
    if val.startswith("UploadFile(") or "Headers(" in val:
        return False
    return True

async def _load_user_by_email(email: str):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text(
                """
                SELECT email, password_hash, digest_frequency, agency_filter, is_active, id
                FROM users
                WHERE email = :email
                LIMIT 1
                """
            ),
            {"email": email.lower().strip()},
        )
        return res.fetchone()


async def _get_user_id(email: str) -> Optional[str]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
            {"email": email},
        )
        row = res.fetchone()
        return row[0] if row else None


async def _auto_accept_invite(email: str) -> None:
    """
    Best-effort: if there's a pending team invite for this email, accept it and link team_id.
    Runs on login/signup to avoid a manual accept step.
    """
    if not email:
        return
    try:
        async with AsyncSessionLocal() as session:
            user_res = await session.execute(
                text("SELECT id FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
                {"email": email},
            )
            urow = user_res.fetchone()
            if not urow:
                return
            user_id = urow[0]

            invite_res = await session.execute(
                text(
                    """
                    SELECT team_id FROM team_members
                    WHERE accepted_at IS NULL AND lower(invited_email) = lower(:email)
                    ORDER BY invited_at DESC
                    LIMIT 1
                    """
                ),
                {"email": email},
            )
            invite_row = invite_res.fetchone()
            team_id = invite_row[0] if invite_row else None

            # If already linked, fall back to most recent membership record.
            if not team_id:
                fallback_res = await session.execute(
                    text(
                        """
                        SELECT team_id FROM team_members
                        WHERE user_id = :uid OR lower(invited_email) = lower(:email)
                        ORDER BY accepted_at DESC NULLS LAST, invited_at DESC
                        LIMIT 1
                        """
                    ),
                    {"uid": user_id, "email": email},
                )
                frow = fallback_res.fetchone()
                if not frow:
                    return
                team_id = frow[0]

            await session.execute(
                text(
                    """
                    UPDATE team_members
                    SET user_id = :uid, accepted_at = COALESCE(accepted_at, CURRENT_TIMESTAMP)
                    WHERE team_id = :team AND lower(invited_email) = lower(:email)
                    """
                ),
                {"team": team_id, "email": email, "uid": user_id},
            )
            await session.execute(
                text("UPDATE users SET team_id = :team WHERE id = :uid"),
                {"team": team_id, "uid": user_id},
            )
            await session.execute(
                text(
                    """
                    DELETE FROM team_members
                    WHERE invited_email = :email AND accepted_at IS NULL AND team_id != :team
                    """
                ),
                {"email": email, "team": team_id},
            )
            await session.commit()
    except SQLAlchemyError:
        # Don't block auth on invite acceptance failures.
        return


# --- signup ----------------------------------------------------------

@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, next: str = "/"):
    user_email = get_current_user_email(request)
    csrf_cookie = request.cookies.get("csrftoken") or secrets.token_urlsafe(32)
    invite_mode = bool((request.query_params.get("invite") or "").strip())
    selected_plan = (request.query_params.get("plan") or "free").lower()
    if selected_plan not in {"free", "starter", "professional", "enterprise"}:
        selected_plan = "free"
    if invite_mode:
        selected_plan = "free"
    paid_flag = (request.query_params.get("paid") or "").strip()
    prefill_email = request.query_params.get("email") or ""
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
              <input type="radio" name="plan_choice" value="{p['key']}" {'checked' if p['key']==selected_plan else ''}>
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
    plan_section = ""
    if not invite_mode:
        plan_section = f"""
      <div class="form-row plan-chooser">
        <div class="plan-chooser-head">
          <div>
            <div class="label-small">Pick your starting plan</div>
            <div class="help-text">Confirm your plan. Paid plans go to Stripe checkout, then you return here to finish signup.</div>
          </div>
          <div class="plan-chooser-note">Change anytime</div>
        </div>
        <div class="plan-tiles">{plan_html}</div>
      </div>
      <div class="form-actions" style="justify-content:space-between; align-items:center;">
        <button class="button-secondary" type="button" id="pay-now-btn">Confirm plan & go to Stripe</button>
        <div style="display:flex; gap:12px; align-items:center;">
          <label style="font-size:13px; color:#374151;"><input type="checkbox" name="remember"> Keep me signed in</label>
          <button class="button-primary" type="submit">Create account & continue</button>
        </div>
      </div>
        """
    else:
        plan_section = """
      <div class="auth-alert" style="color:#166534; border-color:#bbf7d0; background:#ecfdf3;">
        You were invited to a team. No billing required—finish creating your free account to join.
      </div>
      <div class="form-actions" style="justify-content:flex-end; align-items:center;">
        <div style="display:flex; gap:12px; align-items:center;">
          <label style="font-size:13px; color:#374151;"><input type="checkbox" name="remember"> Keep me signed in</label>
          <button class="button-primary" type="submit">Create account & continue</button>
        </div>
      </div>
        """
    body_html = f"""
    <h1 class="auth-title">Create your account</h1>
    <p class="auth-subtext">Start in seconds. {"Join your team with a free account—no billing needed." if invite_mode else "Confirm a plan, finish checkout, then complete signup."}</p>
    {"<div class='auth-alert' style='color:#166534; border-color:#bbf7d0; background:#ecfdf3;'>Payment received for your selected plan. Finish creating your account below.</div>" if paid_flag else ""}

    <form class="auth-form" method="POST" action="/signup">\n        <input type="hidden" name="csrf_token" id="csrf_signup" value="{csrf_cookie}">
      <input type="hidden" name="next" value="{next}">
      <input type="hidden" name="plan" id="plan-hidden" value="{selected_plan}">
      {"<input type='hidden' name='invite' value='1'>" if invite_mode else ""}
      {"<input type='hidden' name='paid' value='1'>" if paid_flag else ""}
      <div class="form-row">
        <div class="form-col">
          <label class="auth-label">First name</label>
          <input class="auth-input" type="text" name="first_name" placeholder="Jane" required />
        </div>
        <div class="form-col">
          <label class="auth-label">Last name</label>
          <input class="auth-input" type="text" name="last_name" placeholder="Doe" required />
        </div>
      </div>
      <div class="form-row">
        <div class="form-col">
          <label class="auth-label">Email</label>
          <input class="auth-input" type="email" name="email" id="signup-email" placeholder="you@company.com" value="{prefill_email}" required />
        </div>
        <div class="form-col">
          <label class="auth-label">Password</label>
          <div class="input-with-toggle">
            <input class="auth-input" id="signup-password" type="password" name="password" placeholder="Create a strong password" required />
            <button type="button" class="pw-toggle" aria-controls="signup-password" aria-label="Show password">Show</button>
          </div>
          <div class="help-text">Minimum 8 characters recommended.</div>
        </div>
      </div>
      <div class="form-row">
        <div class="form-col">
          <label class="auth-label">Primary interest</label>
          <select name="primary_interest">{options_html}</select>
          <div class="help-text">We use this to auto-tailor your welcome dashboard.</div>
        </div>
      </div>
      {plan_section}
      <div class="auth-inline-links" style="justify-content:flex-start;">
        <span>Already have an account? <a href="/login?next={next}">Sign in</a>.</span>
      </div>
    </form>
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
        var hidden = document.getElementById('plan-hidden');
        var emailInput = document.getElementById('signup-email');
        var selectTile = function(tile){{
          var radio = tile.querySelector('input[type=\"radio\"]');
          if(!radio) return;
          radio.checked = true;
          tiles.forEach(function(t){{ t.classList.toggle('selected', t===tile); }});
          if(hidden) hidden.value = radio.value;
        }};
        tiles.forEach(function(tile){{
          if((tile.querySelector('input[type=\"radio\"]') || {{}}).checked) {{
            selectTile(tile);
          }}
          tile.addEventListener('click', function(ev){{
            ev.preventDefault();
            selectTile(tile);
          }});
        }});
        var payBtn = document.getElementById('pay-now-btn');
        if(payBtn){{
          payBtn.addEventListener('click', function(ev){{
            ev.preventDefault();
            var emailVal = emailInput ? (emailInput.value || '').trim() : '';
            if(!emailVal) {{ alert('Enter your email first.'); return; }}
            var planVal = hidden ? (hidden.value || 'free') : 'free';
            var returnTo = '/signup?plan=' + encodeURIComponent(planVal) + '&email=' + encodeURIComponent(emailVal) + '&paid=1';
            window.location.href = '/billing/checkout?plan=' + encodeURIComponent(planVal) + '&email=' + encodeURIComponent(emailVal) + '&return_to=' + encodeURIComponent(returnTo);
          }});
        }}
      }})();
    </script>
    """
    resp = HTMLResponse(auth_shell(body_html, title="Sign up - EasyRFP", wrapper_class="auth-wrapper-wide", card_class="auth-card-wide"))
    resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax")
    return resp


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    remember: bool = Form(False),
    primary_interest: str = Form(DEFAULT_INTEREST_KEY),
    plan: str = Form("free"),
    paid: str = Form(""),
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

    # If the email already exists, prompt login instead of overwriting credentials.
    existing = await _load_user_by_email(email_clean)
    if existing:
        return HTMLResponse(
            auth_shell(
                f"""
                <h1 class="auth-title">Account already exists</h1>
                <div class="auth-alert" style="color:#b91c1c; background:#fef2f2; border-color:#fca5a5;">We found an account for <b>{email_clean}</b>. Please sign in instead of creating a new one.</div>
                <div class="auth-inline-links"><a href="/login?next={next}">Go to login</a></div>
                """,
                title="Account exists",
                wrapper_class="auth-wrapper-wide",
                card_class="auth-card-wide",
            ),
            status_code=400,
        )

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at, primary_interest, onboarding_step, onboarding_completed, first_name, last_name)
                    VALUES (:email, :pw, 'daily', '[]', 1, CURRENT_TIMESTAMP, :interest, 'signup', 0, :first_name, :last_name)
                    ON CONFLICT(email) DO UPDATE SET
                      password_hash = excluded.password_hash,
                      is_active = 1,
                      primary_interest = :interest,
                      onboarding_step = 'signup',
                      first_name = COALESCE(excluded.first_name, users.first_name),
                      last_name = COALESCE(excluded.last_name, users.last_name),
                      onboarding_completed = 0
                """
            ),
            {
                "email": email_clean,
                "pw": pw_hash,
                "interest": interest_choice,
                "first_name": first_name.strip(),
                "last_name": last_name.strip(),
            },
        )
        await session.commit()

    await set_primary_interest(email_clean, interest_choice)
    await record_milestone(email_clean, "signup", {"source": "signup_form"})
    await _auto_accept_invite(email_clean)

    token = create_session_token(email_clean)
    paid_flag = (paid or "").strip()
    if plan_choice != "free" and not paid_flag:
        redirect_to = f"/billing/checkout?plan={plan_choice}"
    else:
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
async def login_form(request: Request, next: str = "/tracker/dashboard"):
    # Do NOT redirect from here; show the form to avoid loops.
    user_email = get_current_user_email(request)
    csrf_cookie = request.cookies.get("csrftoken") or secrets.token_urlsafe(32)
    body_html = f"""
    <h1 class="auth-title">Log in to your account</h1>
    <p class="auth-subtext">Access your dashboard and alerts.</p>
    <form class="auth-form" method="POST" action="/login">
      <input type="hidden" name="csrf_token" id="csrf_login" value="{csrf_cookie}">
      <input type="hidden" name="next" value="{next}">
      <div class="auth-field">
        <label class="auth-label">Email address</label>
        <input class="auth-input" type="email" name="email" placeholder="you@company.com" required />
      </div>
      <div class="auth-field">
        <label class="auth-label">Password</label>
        <div class="input-with-toggle">
          <input class="auth-input" id="login-password" type="password" name="password" placeholder="Your password" required />
          <button type="button" class="pw-toggle" aria-controls="login-password" aria-label="Show password">Show</button>
        </div>
      </div>
      <div class="auth-actions">
        <label class="auth-remember"><input type="checkbox" name="remember"> Keep me signed in</label>
        <button class="auth-submit" type="submit">Log in</button>
      </div>
      <div class="auth-inline-links">
        <span>New to EasyRFP? <a href="/signup?next={next}">Sign up</a></span>
        <a href="/reset">Forgot your password?</a>
      </div>
    </form>
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
    resp = HTMLResponse(auth_shell(body_html, title="Log in - EasyRFP")); resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax"); return resp


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
            auth_shell(
                """
          <h1 class="auth-title">Sign in failed</h1>
          <div class="auth-alert">Invalid email or password.</div>
          <div class="auth-inline-links"><a href="/login">Try again</a></div>
                """,
                title="Login failed",
            ),
            status_code=401,
        )

    db_email, db_pw_hash, *_rest, is_active = row
    if not is_active:
        return HTMLResponse(
            auth_shell(
                """
          <h1 class="auth-title">Account inactive</h1>
          <div class="auth-alert">This account is inactive. Contact support.</div>
                """,
                title="Inactive",
            ),
            status_code=403,
        )

    if not verify_password(password, db_pw_hash):
        return HTMLResponse(
            auth_shell(
                """
          <h1 class="auth-title">Sign in failed</h1>
          <div class="auth-alert">Invalid email or password.</div>
          <div class="auth-inline-links"><a href="/login">Try again</a></div>
                """,
                title="Login failed",
            ),
            status_code=401,
        )

    await _auto_accept_invite(email_clean)

    # Set cookie and redirect
    token = create_session_token(email_clean)
    redirect_to = next if (next and not next.startswith("/login")) else "/tracker/dashboard"
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


# --- Account APIs ----------------------------------------------------
@router.get("/api/account/overview", response_class=JSONResponse)
async def account_overview(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")

    plan_prices = {
        "free": {"label": "Free", "amount": "$0", "period": "/month"},
        "starter": {"label": "Starter", "amount": "$29", "period": "/month"},
        "professional": {"label": "Professional", "amount": "$99", "period": "/month"},
        "enterprise": {"label": "Enterprise", "amount": "$299", "period": "/month"},
    }
    tier_order = {"free": 0, "starter": 1, "professional": 2, "enterprise": 3}

    async with AsyncSessionLocal() as db:
        def _to_iso(val):
            if val is None:
                return None
            if isinstance(val, dt.datetime):
                return val.isoformat()
            try:
                parsed = dt.datetime.fromisoformat(str(val))
                return parsed.isoformat()
            except Exception:
                return str(val)

        next_billing_at = None
        avatar_key = None
        try:
            res = await db.execute(
                text(
                    """
                    SELECT id, email, first_name, last_name, is_active, created_at,
                           COALESCE(Tier, tier) AS tier, team_id,
                           stripe_customer_id, stripe_subscription_id, avatar_key, next_billing_at
                    FROM users
                    WHERE lower(email) = lower(:email)
                    LIMIT 1
                    """
                ),
                {"email": user_email},
            )
            row = res.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            (
                user_id,
                email,
                first_name,
                last_name,
                is_active,
                created_at,
                tier_raw,
                team_id,
                stripe_customer_id,
                stripe_subscription_id,
                avatar_key,
                next_billing_at,
            ) = row
        except Exception:
            # Fallback for older DBs without next_billing_at
            res = await db.execute(
                text(
                    """
                    SELECT id, email, first_name, last_name, is_active, created_at,
                            COALESCE(Tier, tier) AS tier, team_id,
                            stripe_customer_id, stripe_subscription_id
                    FROM users
                    WHERE lower(email) = lower(:email)
                    LIMIT 1
                    """
                ),
                {"email": user_email},
            )
            row = res.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            (
                user_id,
                email,
                first_name,
                last_name,
                is_active,
                created_at,
                tier_raw,
                team_id,
                stripe_customer_id,
                stripe_subscription_id,
            ) = row
        tier_key = (tier_raw or "free").strip().lower()
        owner_tier_key = None
        if team_id:
            try:
                owner_res = await db.execute(
                    text(
                        """
                        SELECT COALESCE(u.Tier, u.tier)
                        FROM teams t
                        LEFT JOIN users u ON u.id = t.owner_user_id
                        WHERE t.id = :team
                        LIMIT 1
                        """
                    ),
                    {"team": team_id},
                )
                owner_tier_key = (owner_res.scalar() or "").strip().lower()
            except Exception:
                owner_tier_key = None
        effective_key = tier_key
        if owner_tier_key and tier_order.get(owner_tier_key, 0) > tier_order.get(tier_key, 0):
            effective_key = owner_tier_key
        plan = plan_prices.get(effective_key, plan_prices["free"]).copy()
        plan["next_billing"] = _to_iso(next_billing_at)

        tracked_res = await db.execute(
            text(
                """
                SELECT COUNT(*) FROM user_bid_trackers
                WHERE (user_id = :uid OR (visibility = 'team' AND :team_id IS NOT NULL AND team_id = :team_id))
                """
            ),
            {"uid": user_id, "team_id": team_id},
        )
        tracked_count = tracked_res.scalar() or 0

        uploads_res = await db.execute(
            text("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM user_uploads WHERE user_id = :uid"),
            {"uid": user_id},
        )
        uploads_row = uploads_res.fetchone() or (0, 0)
        upload_count = uploads_row[0] or 0
        upload_size = uploads_row[1] or 0

        members: list[dict] = []
        team_id_val = team_id
        user_role = "member"
        try:
            user_id_val, team_id_val = await _ensure_team_feature_access(db, user_email)
            if team_id_val:
                member_res = await db.execute(
                    text(
                        """
                        SELECT tm.id, tm.user_id, tm.invited_email, tm.role, tm.accepted_at, tm.invited_at,
                               u.first_name, u.last_name, u.email, u.avatar_key
                        FROM team_members tm
                        LEFT JOIN users u ON u.id = tm.user_id
                        WHERE tm.team_id = :team
                        """
                    ),
                    {"team": team_id_val},
                )
                rows = member_res.fetchall()
                for r in rows:
                    mid, m_user_id, invited_email, m_role, accepted_at, invited_at, f, l, u_email, m_avatar_key = r
                    email_val = u_email or invited_email
                    name_val = " ".join([p for p in [(f or "").strip(), (l or "").strip()] if p]).strip()
                    members.append(
                        {
                            "id": mid,
                            "email": email_val,
                            "name": name_val or (email_val or ""),
                            "role": (m_role or "member").lower(),
                            "accepted": bool(accepted_at),
                            "accepted_at": accepted_at,
                            "invited_at": invited_at,
                            "avatar_url": create_presigned_get(m_avatar_key) if m_avatar_key else None,
                        }
                    )
                    if m_user_id and str(m_user_id) == str(user_id):
                        user_role = (m_role or "member").lower()
        except Exception:
            members = []

        usage = {
            "tracked": tracked_count,
            "documents": {"count": upload_count, "bytes": upload_size},
            "team": len(members) if members else (1 if user_email else 0),
            "token_calls": 0,
        }

        # Recent activity (limit 5, team-aware)
        activity_entries: list[dict] = []
        tracked_rows = await db.execute(
            text(
                """
                SELECT t.created_at, u.email AS who, o.title
                FROM user_bid_trackers t
                JOIN users u ON u.id = t.user_id
                JOIN opportunities o ON o.id = t.opportunity_id
                WHERE (t.user_id = :uid OR (:team_id IS NOT NULL AND t.team_id = :team_id))
                ORDER BY t.created_at DESC
                LIMIT 10
                """
            ),
            {"uid": user_id, "team_id": team_id},
        )
        for r in tracked_rows.fetchall():
            activity_entries.append(
                {
                    "who": r._mapping.get("who"),
                    "verb": "added to tracking",
                    "obj": r._mapping.get("title"),
                    "when": r._mapping.get("created_at"),
                    "type": "track",
                }
            )
        upload_rows = await db.execute(
            text(
                """
                SELECT u.created_at, usr.email AS who, o.title, u.filename
                FROM user_uploads u
                JOIN users usr ON usr.id = u.user_id
                JOIN opportunities o ON o.id = u.opportunity_id
                WHERE (u.user_id = :uid OR (:team_id IS NOT NULL AND usr.team_id = :team_id))
                ORDER BY u.created_at DESC
                LIMIT 10
                """
            ),
            {"uid": user_id, "team_id": team_id},
        )
        for r in upload_rows.fetchall():
            activity_entries.append(
                {
                    "who": r._mapping.get("who"),
                    "verb": f"uploaded {r._mapping.get('filename') or 'a file'}",
                    "obj": r._mapping.get("title"),
                    "when": r._mapping.get("created_at"),
                    "type": "upload",
                }
            )
        # Sort and trim
        try:
            activity_entries.sort(
                key=lambda x: x.get("when") or dt.datetime.utcnow(), reverse=True
            )
        except Exception:
            activity_entries = activity_entries[:]
        activity_entries = activity_entries[:5]
        for entry in activity_entries:
            entry["when"] = _to_iso(entry.get("when"))

        avatar_url = None
        if avatar_key:
            try:
                avatar_url = create_presigned_get(avatar_key)
            except Exception:
                avatar_url = None

    return {
        "user": {
            "email": email,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "name": " ".join([p for p in [first_name or "", last_name or ""] if p]).strip() or email,
            "tier": plan["label"],
            "tier_key": tier_key,
            "role": user_role,
            "email_verified": bool(is_active),
            "created_at": _to_iso(created_at),
            "avatar_url": avatar_url,
        },
        "plan": {
            "label": plan["label"],
            "amount": plan["amount"],
            "period": plan["period"],
            "billing_url": "/billing",
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
        },
        "usage": usage,
        "team": {
            "members": members,
            "team_id": team_id_val,
        },
        "activity": activity_entries,
    }


@router.post("/api/account/profile", response_class=JSONResponse)
async def update_profile(request: Request, payload: dict):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")

    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="First and last name required")

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                UPDATE users
                SET first_name = :fn, last_name = :ln
                WHERE lower(email) = lower(:email)
                """
            ),
            {"fn": first_name, "ln": last_name, "email": user_email},
        )
        await db.commit()
    return {"ok": True}


@router.post("/api/account/avatar", response_class=JSONResponse)
async def upload_avatar(request: Request):
    from app.storage import store_profile_file, create_presigned_get

    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")

    user_id = await _get_user_id(user_email)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    form = await request.form()
    file = form.get("avatar")
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid file type")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    storage_key = store_profile_file(user_id, "avatar", data, file.filename, file.content_type)

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE users SET avatar_key = :key WHERE id = :uid"),
            {"key": storage_key, "uid": user_id},
        )
        await db.commit()

    url = create_presigned_get(storage_key)
    return {"ok": True, "avatar_url": url}


@router.get("/api/company-profile", response_class=JSONResponse)
async def get_company_profile(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")
    user_id = await _get_user_id(user_email)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1"),
            {"uid": user_id},
        )
        row = res.fetchone()
        data = row[0] if row else {}
        # Stored as JSON text; ensure we return a dict for consumers
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        data = data or {}
        files = {}
        for field in FILE_FIELDS:
            key = data.get(field)
            if not _valid_storage_key(key):
                data.pop(field, None)
                data.pop(f"{field}_name", None)
                continue
            files[field] = {
                "key": key,
                "name": data.get(f"{field}_name", ""),
                "url": create_presigned_get(key),
            }
        return {"data": data, "files": files}


@router.get("/api/company-profile/debug", response_class=JSONResponse)
async def debug_company_profile(request: Request):
    """Debug endpoint to see raw profile data and file URL generation."""
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")
    user_id = await _get_user_id(user_email)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1"),
            {"uid": user_id},
        )
        row = res.fetchone()
        raw_data = row[0] if row else None

    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            pass

    debug_info = {
        "user_id": user_id,
        "raw_data_type": str(type(raw_data)),
        "has_signature_image": bool(raw_data and raw_data.get("signature_image")),
        "signature_image_key": raw_data.get("signature_image") if raw_data else None,
        "signature_image_name": raw_data.get("signature_image_name") if raw_data else None,
        "use_s3": USE_S3,
    }

    if raw_data and raw_data.get("signature_image"):
        try:
            url = create_presigned_get(raw_data["signature_image"])
            debug_info["signature_url_generated"] = url
            debug_info["signature_url_error"] = None
        except Exception as e:
            debug_info["signature_url_generated"] = None
            debug_info["signature_url_error"] = str(e)

    return debug_info


@router.post("/api/company-profile", response_class=JSONResponse)
async def save_company_profile(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")
    user_id = await _get_user_id(user_email)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    content_type = request.headers.get("content-type", "").lower()
    payload = {}
    files_meta = {}

    # Load existing profile so we can preserve stored file keys on partial updates
    async with AsyncSessionLocal() as db:
        existing_res = await db.execute(
            text("SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1"),
            {"uid": user_id},
        )
        existing_row = existing_res.fetchone()
        existing_data = {}
        if existing_row and existing_row[0]:
            try:
                existing_data = existing_row[0] if isinstance(existing_row[0], dict) else json.loads(existing_row[0])
            except Exception:
                existing_data = {}

    if content_type.startswith("application/json"):
        # Fallback for older clients
        payload = await request.json()
    else:
        form = await request.form()
        for key, val in form.multi_items():
            if isinstance(val, UploadFile):
                if not val.filename:
                    continue
                safe_name = (val.filename or "").strip()
                ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
                if ext and ext not in PROFILE_ALLOWED_EXT:
                    raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")
                mime = (val.content_type or "").lower()
                if mime and PROFILE_ALLOWED_MIME and mime not in PROFILE_ALLOWED_MIME:
                    raise HTTPException(status_code=400, detail=f"Unsupported MIME type: {mime}")
                data = await val.read()
                if not data:
                    continue
                if len(data) > PROFILE_MAX_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"File too large (> {PROFILE_MAX_MB} MB)")
                storage_key = store_profile_file(user_id, key, data, val.filename, val.content_type)
                payload[key] = storage_key
                payload[f"{key}_name"] = safe_name
                files_meta[key] = {
                    "key": storage_key,
                    "name": safe_name,
                    "url": create_presigned_get(storage_key),
                }
            else:
                # Ignore non-file values for file fields to avoid storing stringified UploadFile objects
                if key in FILE_FIELDS:
                    continue
                # Handle repeated keys by joining into comma-separated string
                if key in payload:
                    if isinstance(payload[key], list):
                        payload[key].append(str(val))
                    else:
                        payload[key] = [payload[key], str(val)]
                else:
                    payload[key] = str(val)

        # Flatten any lists to comma-separated strings
        for k, v in list(payload.items()):
            if isinstance(v, list):
                payload[k] = ",".join(v)

    merged_data = existing_data.copy()

    # Apply non-file fields from the incoming payload
    for key, value in payload.items():
        if key in FILE_FIELDS or (key.endswith("_name") and key[:-5] in FILE_FIELDS):
            continue
        merged_data[key] = value

    # Handle file fields: prefer new upload/value; otherwise keep existing keys/names
    for field in FILE_FIELDS:
        incoming_val = payload.get(field)
        incoming_name = payload.get(f"{field}_name")

        has_incoming_val = incoming_val not in (None, "", "null", "undefined")
        has_incoming_name = incoming_name not in (None, "", "null", "undefined")

        if has_incoming_val:
            merged_data[field] = incoming_val
        elif field in existing_data:
            merged_data[field] = existing_data[field]

        if has_incoming_name:
            merged_data[f"{field}_name"] = incoming_name
        elif f"{field}_name" in existing_data:
            merged_data[f"{field}_name"] = existing_data[f"{field}_name"]

        # Drop invalid storage keys that may have been stringified UploadFile objects
        if field in merged_data and not _valid_storage_key(merged_data.get(field)):
            merged_data.pop(field, None)
            merged_data.pop(f"{field}_name", None)

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO company_profiles (id, user_id, data, created_at, updated_at)
                VALUES (:id, :uid, :data, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                  data = excluded.data,
                  updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"id": secrets.token_urlsafe(16), "uid": user_id, "data": json.dumps(merged_data)},
        )
        await db.commit()
    file_keys = [k for k in merged_data if k in FILE_FIELDS and _valid_storage_key(merged_data.get(k))]
    try:
        saved_files = {
            field: {
                "key": merged_data.get(field),
                "name": merged_data.get(f"{field}_name", ""),
                "url": create_presigned_get(merged_data.get(field)) if merged_data.get(field) else None,
            }
            for field in file_keys
        }
    except Exception:
        saved_files = files_meta
    logging.info(
        f"Saved company profile for user {user_id}: "
        f"{len(merged_data)} fields, "
        f"{len(file_keys)} files"
    )
    return {"ok": True, "files": saved_files or files_meta}


# --- minimal /account (optional) ------------------------------------

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        return RedirectResponse("/login?next=/account", status_code=303)

    static_account = Path(__file__).resolve().parent.parent / "web" / "static" / "account.html"
    return FileResponse(static_account)


@router.get("/account/team", response_class=HTMLResponse)
async def team_settings(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        return RedirectResponse("/login?next=/account/team", status_code=303)

@router.get("/account/preferences", response_class=HTMLResponse)
async def account_preferences_redirect():
    return RedirectResponse("/preferences", status_code=303)

    body = """
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
    <div id="member-status" class="muted" style="margin-top:6px;"></div>
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
  const memberStatus = document.getElementById("member-status");
  const currentUser = "__CURRENT_USER__".toLowerCase();
  const roleOptions = [
    { value: "manager", label: "Manager" },
    { value: "member", label: "Member" },
    { value: "viewer", label: "Viewer" },
  ];

  function currentUserRole(members){
    const mine = members.find(m => (m.user_email || "").toLowerCase() === currentUser);
    return (mine && (mine.role || "")).toLowerCase();
  }

  function renderMembers(members){
    seatEl.textContent = members.length;
    if (!members.length){
      listEl.innerHTML = "<li class='muted'>No team members yet.</li>";
      return;
    }
    const myRole = currentUserRole(members);
    listEl.innerHTML = members.map(m => `
      <li>
        <div>
          <div><b>${m.user_email || m.invited_email}</b></div>
          <div class="muted">${m.user_id ? "Accepted" : "Pending invite"} - Role: ${m.role}</div>
        </div>
        <div class="member-actions">
          <span class="pill ${m.user_id ? "active" : "pending"}">${m.user_id ? "Active" : "Pending"}</span>
          ${
            ((m.role || "").toLowerCase() !== "owner" && (m.user_email || "").toLowerCase() !== currentUser)
              ? `<button class="btn-ghost remove-btn" data-id="${m.id}" data-email="${m.user_email || m.invited_email || ""}">Remove</button>`
              : ""
          }
          ${
            (myRole === "owner" && (m.role || "").toLowerCase() !== "owner")
              ? `<select class="role-select" data-id="${m.id}">
                  ${roleOptions.map(opt => `<option value="${opt.value}" ${opt.value === (m.role || "").toLowerCase() ? "selected" : ""}>${opt.label}</option>`).join("")}
                 </select>`
              : ""
          }
        </div>
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
  listEl.addEventListener("click", async function(ev){
    const btnEl = ev.target.closest(".remove-btn");
    if (!btnEl) return;
    const memberId = btnEl.getAttribute("data-id");
    const label = btnEl.getAttribute("data-email") || "this member";
    if (!memberId) return;
    if (!confirm("Remove " + label + " from the team?")) return;
    btnEl.disabled = true;
    if (memberStatus) memberStatus.textContent = "Removing " + label + "...";
    try{
      const res = await fetch("/api/team/members/" + memberId + "/remove", {
        method:"POST",
        credentials:"include",
        headers:{ "X-CSRF-Token": getCSRF() || "" }
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      if (memberStatus) memberStatus.textContent = "Removed " + label + ".";
      loadMembers();
    }catch(err){
      if (memberStatus) memberStatus.textContent = "Could not remove member (owner access required).";
    }finally{
      btnEl.disabled = false;
      if (memberStatus) setTimeout(() => { memberStatus.textContent = ""; }, 4000);
    }
  });
  listEl.addEventListener("change", async function(ev){
    const sel = ev.target.closest(".role-select");
    if (!sel) return;
    const memberId = sel.getAttribute("data-id");
    const newRole = sel.value;
    if (!memberId || !newRole) return;
    sel.disabled = true;
    if (memberStatus) memberStatus.textContent = "Updating role...";
    try{
      const res = await fetch("/api/team/members/" + memberId + "/role", {
        method:"POST",
        credentials:"include",
        headers:{ "Content-Type":"application/json", "X-CSRF-Token": getCSRF() || "" },
        body: JSON.stringify({ role: newRole })
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      if (memberStatus) memberStatus.textContent = "Role updated.";
      loadMembers();
    }catch(err){
      if (memberStatus) memberStatus.textContent = "Could not update role (owner only).";
    }finally{
      sel.disabled = false;
      if (memberStatus) setTimeout(() => { memberStatus.textContent = ""; }, 4000);
    }
  });
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
async def accept_invite_ui(request: Request, email: str = ""):
    """
    Accept screen for invited users. If not signed in, show login / signup options (no billing for invitees).
    """
    user_email = get_current_user_email(request)
    if not user_email:
        invite_email = (email or "").strip()
        signup_href = f"/signup?next=/team/accept&plan=free&invite=1"
        if invite_email:
            signup_href += f"&email={invite_email}"
        body = f"""
        <section class="card" style="max-width:620px; margin:0 auto; text-align:center;">
          <h2 class="section-heading">Join your team</h2>
          <p class="subtext">Sign in or create an account to accept the invite{f" for <b>{invite_email}</b>" if invite_email else ""}. No billing required for team members.</p>
          <div style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-top:16px;">
            <a class="button-primary" href="/login?next=/team/accept">Sign in</a>
            <a class="button-secondary" href="{signup_href}">Create account</a>
          </div>
        </section>
        """
        return HTMLResponse(page_shell(body, title="Accept Team Invite", user_email=None))

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
