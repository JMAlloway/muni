# app/routers/onboarding.py

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from app.core.db_core import engine
from app.api._layout import page_shell
from app.auth.auth_utils import require_login
from app.auth.session import get_current_user_email
from app.services import mark_onboarding_completed, record_milestone
import json
from typing import List, Optional


router = APIRouter(tags=["onboarding"])


# --- helpers ---------------------------------------------------------------

AGENCIES_LIST = [
    "City of Columbus",
    "City of Gahanna",
    "City of Grove City",
    "Delaware County",
    "Franklin County",
    "Union County",
    "Licking County",
    "Madison County",
]

INDUSTRIES_LIST = [
    "Construction",
    "IT / Software / Cyber",
    "Landscaping / Grounds",
    "Janitorial / Cleaning",
    "Consulting / Professional Services",
    "Other / Not Listed",
]

FREQUENCIES_LIST = ["daily", "weekly", "none"]
ONBOARDING_STEPS = {"signup", "browsing", "tracked_first", "completed"}


async def _load_existing_prefs(user_email: str):
    """
    Pull saved onboarding prefs for this user (if any).
    Returns dict with agencies[], keywords[], frequency.
    """
    async with engine.begin() as conn:
        pref_res = await conn.execute(
            text(
                """
                SELECT agencies, keywords, frequency
                FROM user_preferences
                WHERE user_email = :email
                """
            ),
            {"email": user_email},
        )
        row = pref_res.first()

    if not row:
        return {
            "agencies": [],
            "keywords": [],
            "frequency": "weekly",
        }

    raw_agencies, raw_keywords, raw_frequency = row

    # agencies
    try:
        agencies_saved = json.loads(raw_agencies) if raw_agencies else []
        if not isinstance(agencies_saved, list):
            agencies_saved = []
    except Exception:
        agencies_saved = []

    # keywords
    try:
        keywords_saved = json.loads(raw_keywords) if raw_keywords else []
        if not isinstance(keywords_saved, list):
            keywords_saved = []
    except Exception:
        keywords_saved = []

    freq_saved = raw_frequency or "weekly"
    if freq_saved not in FREQUENCIES_LIST:
        freq_saved = "weekly"

    return {
        "agencies": agencies_saved,
        "keywords": keywords_saved,
        "frequency": freq_saved,
    }


def _render_form(
    user_email: str,
    agencies_selected: List[str],
    keywords_list: List[str],
    frequency_selected: str,
    error_msg: Optional[str] = None,
    success_msg: Optional[str] = None,
) -> str:
    """
    Build the onboarding form HTML.
    We pass error_msg or success_msg when needed.
    """

    # agencies checkboxes
    agency_check_html = "".join(
        (
            "<label class='choice-row'>"
            f"<input type='checkbox' name='agencies' value='{a}' "
            f"{'checked' if a in agencies_selected else ''} />"
            f"<span>{a}</span>"
            "</label>"
        )
        for a in AGENCIES_LIST
    )

    # industry checkboxes (future use, not yet persisted)
    industry_check_html = "".join(
        (
            "<label class='choice-row'>"
            f"<input type='checkbox' name='industries' value='{i}' />"
            f"<span>{i}</span>"
            "</label>"
        )
        for i in INDUSTRIES_LIST
    )

    # freq dropdown
    def _sel(val: str) -> str:
        return "selected" if val == frequency_selected else ""

    freq_opts_html = "".join(
        (
            f"<option value='{f}' {_sel(f)}>"
            f"{'Daily – new/changed in last 24h' if f=='daily' else ''}"
            f"{'Weekly – last 7 days' if f=='weekly' else ''}"
            f"{'No emails for now' if f=='none' else ''}"
            "</option>"
        )
        for f in FREQUENCIES_LIST
    )

    # comma-separated keywords string
    keywords_str = ", ".join(keywords_list)

    # alert banners
    alert_html = ""
    if error_msg:
        alert_html = f"""
        <div class="alert-banner error">
            <div class="alert-title">Please fix and resubmit</div>
            <div class="alert-desc">{error_msg}</div>
        </div>
        """
    elif success_msg:
        alert_html = f"""
        <div class="alert-banner success">
            <div class="alert-title">Saved ✔</div>
            <div class="alert-desc">{success_msg}</div>
        </div>
        """

    # MAIN BODY
    body_html = f"""
    <section class="card" style="max-width:780px;">
        <h2 class="section-heading">Tell us what to watch for</h2>
        <p class="subtext">
            We'll personalize your dashboard and email you when there's
            something worth bidding on.
        </p>

        {alert_html}

        <form method="POST" action="/onboarding" class="onboard-form">

            <!-- STEP 1 -->
            <div class="onboard-step">
                <div class="step-head">
                    <div class="step-num">1</div>
                    <div class="step-copy">
                        <div class="step-title">What kind of work do you do?</div>
                        <div class="step-desc">Pick anything close. This helps us tag opportunities for you.</div>
                    </div>
                </div>
                <div class="step-body">
                    {industry_check_html}
                    <div class="muted small">
                        Don’t see your trade? Pick “Other / Not Listed”.
                    </div>
                </div>
            </div>

            <!-- STEP 2 -->
            <div class="onboard-step">
                <div class="step-head">
                    <div class="step-num">2</div>
                    <div class="step-copy">
                        <div class="step-title">Who do you want to sell to?</div>
                        <div class="step-desc">We'll pin your dashboard to these buyers.</div>
                    </div>
                </div>
                <div class="step-body">
                    {agency_check_html}
                    <div class="muted small">
                        Leave everything unchecked and we’ll show all agencies we monitor.
                    </div>
                </div>
            </div>

            <!-- STEP 3 -->
            <div class="onboard-step">
                <div class="step-head">
                    <div class="step-num">3</div>
                    <div class="step-copy">
                        <div class="step-title">How often should we email you leads?</div>
                        <div class="step-desc">You can change this any time under Account.</div>
                    </div>
                </div>
                <div class="step-body">
                    <select name="frequency" required>
                        {freq_opts_html}
                    </select>
                    <div class="muted small" style="margin-top:4px;">
                        Daily = "what changed in last 24h". Weekly = last 7 days.
                    </div>
                </div>
            </div>

            <!-- STEP 4 -->
            <div class="onboard-step">
                <div class="step-head">
                    <div class="step-num">4</div>
                    <div class="step-copy">
                        <div class="step-title">Keywords (optional)</div>
                        <div class="step-desc">
                            We'll flag bids that mention these phrases in the description or title.
                        </div>
                    </div>
                </div>
                <div class="step-body">
                    <input
                        type="text"
                        name="keywords"
                        value="{keywords_str}"
                        placeholder="roofing, hvac service, parking lot striping"
                        style="width:100%;max-width:480px;"
                    />
                    <div class="muted small" style="margin-top:4px;">
                        Comma-separated. We'll watch for each word/phrase.
                    </div>
                </div>
            </div>

            <!-- CTA -->
            <div class="onboard-footer">
                <button class="button-primary" type="submit">
                    Save my preferences →
                </button>

                <div class="muted small" style="margin-top:12px;">
                    Or <a class="cta-link" href="/opportunities?agency=">skip for now</a>
                    and just see everything.
                </div>
            </div>

        </form>
    </section>

    <section class="card" style="max-width:780px;">
        <div class="mini-head">Application Variables</div>
        <div class="mini-desc">
            Save your organization details once (legal name, EIN, contacts, certifications) and reuse them when completing applications.
        </div>
        <a class="button-primary" href="/preferences/application">Manage Application Variables</a>
    </section>

    <section class="card" style="max-width:780px;">
        <div class="mini-head">What happens next?</div>
        <div class="mini-desc">
            • Your dashboard filters to the buyers you picked.<br/>
            • We send you a digest at the cadence you chose.<br/>
            • You can come back here or go to <a class="cta-link" href="/account">Account</a> to edit.
        </div>
    </section>

    <style>
        .onboard-form .onboard-step {{
            border-top: 1px solid #e5e7eb;
            padding-top:16px;
            margin-top:16px;
        }}
        .step-head {{
            display:flex;
            align-items:flex-start;
            gap:12px;
        }}
        .step-num {{
            background: var(--accent-bg);
            color: var(--accent-text);
            font-weight:600;
            font-size:13px;
            line-height:24px;
            width:24px;
            height:24px;
            border-radius:999px;
            text-align:center;
        }}
        .step-title {{
            font-size:14px;
            font-weight:600;
            color:#111827;
            line-height:1.3;
        }}
        .step-desc {{
            font-size:12px;
            color:#4b5563;
            line-height:1.4;
        }}
        .step-body {{
            margin-top:12px;
            margin-left:36px;
            font-size:13px;
            color:#111827;
            line-height:1.45;
        }}
        .choice-row {{
            display:flex;
            align-items:flex-start;
            gap:8px;
            font-size:13px;
            font-weight:500;
            color:#111;
            line-height:1.4;
            margin-bottom:6px;
        }}
        .choice-row input[type='checkbox'] {{
            margin-top:2px;
            accent-color: var(--accent-bg);
        }}
        .muted.small {{
            font-size:12px;
            color:#4b5563;
        }}
        .onboard-footer {{
            margin-top:24px;
            margin-left:36px;
        }}
        .alert-banner {{
            border-radius:8px;
            padding:12px 16px;
            font-size:13px;
            line-height:1.4;
            margin-bottom:16px;
        }}
        .alert-banner.error {{
            background:#FEF2F2;
            border:1px solid #FECACA;
            color:#B91C1C;
        }}
        .alert-banner.success {{
            background:#ECFDF5;
            border:1px solid #A7F3D0;
            color:#065F46;
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

    return body_html


def _render_success(user_email: str, agencies: List[str], freq: str, keywords_list: List[str]) -> str:
    """
    After POST success, show a confirmation card instead of blind redirect.
    """
    agencies_label = ", ".join(agencies) if agencies else "All Agencies"
    keywords_label = ", ".join(keywords_list) if keywords_list else "—"

    body_html = f"""
    <section class="card" style="max-width:780px;">
        <h2 class="section-heading">All set ✅</h2>
        <p class="subtext" style="margin-bottom:1rem;">
            You're now tracking bids for <b>{agencies_label}</b>.
            We'll email <b>{user_email}</b> <b>{freq}</b>.
        </p>

        <div class="mini-head">Your keywords</div>
        <div class="mini-desc" style="margin-bottom:1rem;">
            <code class="chip">{keywords_label}</code>
        </div>

        <a class="button-primary" href="/opportunities">
            View my opportunities →
        </a>

        <div class="muted" style="margin-top:12px;font-size:12px;line-height:1.4;">
            You can update this anytime in
            <a class="cta-link" href="/account">Account</a>.
        </div>
    </section>

    <section class="card" style="max-width:780px;">
        <div class="mini-head">How alerts work</div>
        <div class="mini-desc">
            Daily emails = new / changed in the last 24 hours.
            Weekly = last 7 days.
        </div>
    </section>
    """
    return body_html


# --- routes ----------------------------------------------------------------

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_get(request: Request):
    """
    Guided onboarding form for logged-in users.
    If they already filled it out, we still show it (so they can edit).
    """
    user_email = await require_login(request)
    if isinstance(user_email, RedirectResponse):
        return user_email

    existing = await _load_existing_prefs(user_email)

    html_body = _render_form(
        user_email=user_email,
        agencies_selected=existing["agencies"],
        keywords_list=existing["keywords"],
        frequency_selected=existing["frequency"],
        error_msg=None,
        success_msg=None,
    )

    return HTMLResponse(
        page_shell(
            html_body,
            title="Onboarding – Muni Alerts",
            user_email=user_email,
        )
    )


@router.post("/onboarding", response_class=HTMLResponse)
async def onboarding_post(
    request: Request,
    agencies: List[str] = Form([]),
    industries: List[str] = Form([]),  # still placeholder, not persisted
    frequency: str = Form("weekly"),
    keywords: str = Form(""),
):
    """
    Save prefs to user_preferences + users.
    Return success view if valid, or redisplay form w/ inline error if not.
    """
    user_email = await require_login(request)
    if isinstance(user_email, RedirectResponse):
        return user_email

    # --- normalize inputs ---
    # frequency
    freq_clean = (frequency or "").strip().lower()
    if freq_clean not in FREQUENCIES_LIST:
        freq_clean = "weekly"

    # agencies
    # (we'll store exactly what they selected, no forced lowercase, but drop blanks)
    agencies_clean = [a.strip() for a in agencies if a.strip()]

    # keywords
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]

    # basic validation: require at least something to work with:
    # right now, we won't force them to pick industries or agencies.
    # but if they somehow gave us an absurd freq, we already fixed it above.
    # So "invalid" here mainly means "none", which is never invalid.
    validation_error = None

    # write to DB if no validation error
    if not validation_error:
        agencies_json = json.dumps(agencies_clean)
        keywords_json = json.dumps(keyword_list)

        # upsert into user_preferences
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO user_preferences (
                        user_email,
                        agencies,
                        keywords,
                        frequency,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :email,
                        :agencies,
                        :keywords,
                        :frequency,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(user_email)
                    DO UPDATE SET
                        agencies   = :agencies,
                        keywords   = :keywords,
                        frequency  = :frequency,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "email": user_email,
                    "agencies": agencies_json,
                    "keywords": keywords_json,
                    "frequency": freq_clean,
                },
            )

        # mirror into users table for digest job
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO users (
                        email,
                        digest_frequency,
                        agency_filter,
                        is_active,
                        created_at
                    )
                    VALUES (
                        :email,
                        :freq,
                        :agencies,
                        1,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(email)
                    DO UPDATE SET
                        digest_frequency = :freq,
                        agency_filter    = :agencies,
                        is_active        = 1
                    """
                ),
                {
                    "email": user_email.lower().strip(),
                    "freq": freq_clean,
                    "agencies": agencies_json,
                },
            )

        # show success confirmation view instead of blind redirect
        success_body = _render_success(
            user_email=user_email,
            agencies=agencies_clean,
            freq=freq_clean,
            keywords_list=keyword_list,
        )
        return HTMLResponse(
            page_shell(
                success_body,
                title="Preferences Saved – Muni Alerts",
                user_email=user_email,
            )
        )

    # if we did hit validation error, re-render form with the user's choices still filled in
    html_body = _render_form(
        user_email=user_email,
        agencies_selected=agencies_clean,
        keywords_list=keyword_list,
        frequency_selected=freq_clean,
        error_msg=validation_error,
        success_msg=None,
    )
    return HTMLResponse(
        page_shell(
            html_body,
            title="Onboarding – Muni Alerts",
            user_email=user_email,
        ),
        status_code=400,
    )

@router.post("/api/onboarding/milestone")
async def api_onboarding_milestone(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    step = (payload.get('step') or '').strip().lower()
    if step not in ONBOARDING_STEPS:
        raise HTTPException(status_code=400, detail="Invalid step")

    metadata = payload.get('metadata')
    if not isinstance(metadata, dict):
        metadata = {}

    advanced = await record_milestone(user_email, step, metadata)
    return {'ok': True, 'advanced': advanced}


@router.post("/api/onboarding/dismiss")
async def api_onboarding_dismiss(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await mark_onboarding_completed(user_email, {"source": "user-dismiss"})
    return {'ok': True}
