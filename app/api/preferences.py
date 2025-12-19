# app/routers/preferences.py

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from typing import List
import json
import secrets
import re
from urllib.parse import parse_qs

from app.core.db import AsyncSessionLocal
from app.api._layout import page_shell
from app.auth.session import get_current_user_email
from app.services import mark_onboarding_completed

router = APIRouter(tags=["preferences"])

@router.get("/preferences", response_class=HTMLResponse)
async def get_preferences(request: Request):
    return RedirectResponse("/account#tab-notifications", status_code=301)


@router.get("/preferences-legacy", response_class=HTMLResponse)
async def get_preferences_legacy(request: Request):
    user_email = get_current_user_email(request)

    known_agencies = [
        "City of Columbus",
        "City of Grove City",
        "City of Gahanna",
        "City of Marysville",
        "City of Whitehall",
        "City of Grandview Heights",
        "city of Worthington",
        "Solid Waste Authority of Central Ohio (SWACO)",
        "Central Ohio Transit Authority (COTA)",
        "Franklin County, Ohio",
        "City of Westerville",
        "Columbus Metropolitan Library",
        "Columbus Metropolitan Housing Authority",
        "Columbus and Franklin County Metro Parks",
        "Columbus Regional Airport Authority (CRAA)",
        "Mid-Ohio Regional Planning Commission (MORPC)",
        "Dublin City Schools",
        "Village of Minerva Park",
        "City of New Albany",
        "Ohio Buys",
    ]

    agencies_checkboxes = []
    for ag in known_agencies:
        agencies_checkboxes.append(
            f"<label class='agency-choice'>"
            f"<input type='checkbox' name='agency' value='{ag}' />"
            f"{ag}"
            "</label>"
        )

    body_html = f"""
    <section class="card">
        <h2 class="section-heading">Get Bid Alerts</h2>
        <p class="subtext">
            We'll send you new & updated opportunities either every morning
            (daily digest) or every Friday (weekly digest).
        </p>

        <form method="POST" action="/preferences">
            <div class="form-row">
                <div class="form-col">
                    <label class="label-small">Your email</label>
                    <input type="text" name="email" placeholder="you@company.com" required />
                    <div class="muted" style="margin-top:4px;">
                        Alerts will go here.
                    </div>
                </div>

                <div class="form-col">
                    <label class="label-small">How often?</label>
                    <select name="frequency" required>
                        <option value="daily">Daily (last 24h of activity)</option>
                        <option value="weekly">Weekly (last 7 days)</option>
                        <option value="none">No email yet</option>
                    </select>
                    <div class="muted" style="margin-top:4px;">
                        You can change this later.
                    </div>
                </div>
            </div>

            <div class="form-row">
                <div class="form-col">
                    <label class="label-small">Mobile for SMS alerts</label>
                    <input type="text" name="sms_phone" placeholder="(555) 555-5555" />
                    <label class="label-small" style="font-weight:400;margin-top:6px;">
                        <input type="checkbox" name="sms_opt_in" value="1" /> Send me SMS alerts (due soon + digest)
                    </label>
                    <div class="muted" style="margin-top:4px;">
                        SMS available on paid plans; carrier rates may apply.
                    </div>
                </div>
                <div class="form-col">
                    <label class="label-small">Plan</label>
                    <select name="tier">
                        <option value="free">Free</option>
                        <option value="starter">Starter</option>
                        <option value="professional">Professional</option>
                        <option value="enterprise">Enterprise</option>
                    </select>
                    <div class="muted" style="margin-top:4px;">
                        SMS alerts require Starter, Professional, or Enterprise.
                    </div>
                </div>
            </div>

            <div style="margin-bottom:24px;">
                <label class="label-small">Which agencies matter to you?</label>
                <div class="agency-grid">
                    {''.join(agencies_checkboxes)}
                </div>
                <div class="muted" style="margin-top:4px;">
                    If you leave all unchecked, you'll get everything we track.
                </div>
            </div>

            <button class="button-primary" type="submit">Save My Alerts</button>
      </form>
    </section>

    <section class="card">
        <div class="mini-head">Application Variables</div>
        <div class="mini-desc">
            Save your organization details once (legal name, EIN, contacts, certifications) and reuse them when completing applications.
        </div>
        <a class="button-primary" href="/preferences/application">Manage Application Variables</a>
    </section>

    <section class="card">
        <div class="mini-head">What you'll receive</div>
        <div class="mini-desc">
            Each alert groups opportunities by agency, shows titles, due dates,
            and direct links back to the official procurement portal.
        </div>
        <ul style="margin:12px 0 0 18px;padding:0;font-size:13px;color:#374151;line-height:1.4;">
            <li>You don't have to monitor multiple portals manually</li>
            <li>You catch bids in time to respond</li>
            <li>You stay ahead of deadlines</li>
        </ul>
    </section>
    """

    return HTMLResponse(page_shell(body_html, title="EasyRFP Preferences", user_email=user_email))


@router.post("/preferences", response_class=HTMLResponse)
async def post_preferences(
    request: Request,
    email: str = Form(...),
    frequency: str = Form(...),
    agency: List[str] = Form([]),
    sms_phone: str = Form(""),
    sms_opt_in: str = Form(""),
    tier: str = Form("free"),
):
    user_email = get_current_user_email(request)

    email_clean = email.strip().lower()
    freq_clean = frequency.strip().lower()
    if freq_clean not in ("daily", "weekly", "none"):
        freq_clean = "daily"

    tier_clean = tier.strip().lower()
    if tier_clean not in ("free", "starter", "professional", "enterprise"):
        tier_clean = "free"

    phone_clean = sms_phone.strip()
    opt_in_flag = sms_opt_in.strip() != ""
    phone_verified = 1 if (opt_in_flag and phone_clean) else 0

    agencies_json = json.dumps(agency)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO users (email, digest_frequency, agency_filter, created_at, sms_phone, sms_opt_in, sms_phone_verified, tier)
                VALUES (:email, :freq, :agencies, CURRENT_TIMESTAMP, :sms_phone, :sms_opt_in, :sms_verified, :tier)
                ON CONFLICT(email) DO UPDATE SET
                    digest_frequency = excluded.digest_frequency,
                    agency_filter = excluded.agency_filter,
                    sms_phone = excluded.sms_phone,
                    sms_opt_in = excluded.sms_opt_in,
                    sms_phone_verified = excluded.sms_phone_verified,
                    tier = excluded.tier
            """),
            {
                "email": email_clean,
                "freq": freq_clean,
                "agencies": agencies_json,
                "sms_phone": phone_clean,
                "sms_opt_in": 1 if opt_in_flag else 0,
                "sms_verified": phone_verified,
                "tier": tier_clean,
            },
        )
        await session.commit()

    agencies_label = ", ".join(agency) if agency else "All"

    body_html = f"""
    <section class="card">
        <h2 class="section-heading">You're on the list.</h2>
        <p class="subtext" style="margin-bottom:16px;">
            We'll send opportunities to <b>{email_clean}</b> at <b>{freq_clean}</b> frequency.
        </p>

        <div class="mini-head" style="margin-bottom:4px;">Agencies selected</div>
        <div class="mini-desc" style="margin-bottom:16px;">
            <code class="chip">{agencies_label}</code>
        </div>

        <a class="button-primary" href="/opportunities">See current bids</a>
        <div class="muted" style="margin-top:12px;">
            Want to edit these later? <a class="cta-link" href="/signup">Create an account</a>
            to manage settings.
        </div>
    </section>

    <section class="card">
        <div class="subtext">
            Daily emails include only opportunities created or updated in the last 24 hours.
            Weekly emails include the past 7 days.
        </div>
    </section>
    """

    return HTMLResponse(page_shell(body_html, title="Alerts Saved", user_email=user_email))


@router.post("/preferences/quick-setup")
async def quick_preferences(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    agencies_raw = payload.get("agencies") or []
    if not isinstance(agencies_raw, list):
        raise HTTPException(status_code=400, detail="Agencies must be a list")
    agencies_clean = [str(a).strip() for a in agencies_raw if str(a).strip()]

    frequency = (payload.get("frequency") or "weekly").strip().lower()
    if frequency not in ("daily", "weekly", "none"):
        frequency = "weekly"

    agencies_json = json.dumps(agencies_clean)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO user_preferences (user_email, agencies, keywords, frequency, created_at, updated_at)
                VALUES (:email, :agencies, '[]', :frequency, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(user_email) DO UPDATE SET
                    agencies   = :agencies,
                    frequency  = :frequency,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "email": user_email,
                "agencies": agencies_json,
                "frequency": frequency,
            },
        )

        await session.execute(
            text(
                """
                INSERT INTO users (email, digest_frequency, agency_filter, created_at)
                VALUES (:email, :freq, :agencies, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    digest_frequency = :freq,
                    agency_filter    = :agencies
                """
            ),
            {
                "email": user_email,
                "freq": frequency,
                "agencies": agencies_json,
            },
        )

        await session.commit()

    await mark_onboarding_completed(user_email, {"source": "quick-setup"})
    return {"ok": True}


# ---------------------------------------------------------------------
# Application Variables (per-user JSON profile)
# ---------------------------------------------------------------------

@router.get("/preferences/application", response_class=HTMLResponse)
async def application_vars_form(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        body = """
        <section class=\"card\">\n  <h2 class=\"section-heading\">Sign in required</h2>\n  <p class=\"subtext\">Please log in to manage your application variables.</p>\n  <a class=\"button-primary\" href=\"/login?next=/preferences/application\">Sign in</a>\n</section>
        """
        return HTMLResponse(page_shell(body, title="Application Variables", user_email=None))

    # Load any existing stored data
    data = {}
    updated_label = ""
    csrf_cookie = request.cookies.get("csrftoken") or secrets.token_urlsafe(32)
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT data, updated_at FROM user_application_vars WHERE user_email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if row and row[0] is not None:
            try:
                val = row[0]
                if isinstance(val, dict):
                    data = val
                elif isinstance(val, (str, bytes)):
                    s = val.decode() if isinstance(val, bytes) else val
                    data = json.loads(s) if s else {}
                else:
                    # Fallback: try JSON decoding of stringified value
                    data = json.loads(str(val))
            except Exception:
                data = {}
        # updated_at label
        try:
            updated_raw = row[1] if row and len(row) > 1 else None
            if updated_raw:
                updated_label = str(updated_raw)
        except Exception:
            updated_label = ""

    def v(key, default=""):
        try:
            return (data or {}).get(key) or default
        except Exception:
            return default
    def e(key):
        return ''

    cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, private"}

    body_html = f"""
    <section class=\"card\">
      <h2 class=\"section-heading\">Application Variables</h2>
      <p class=\"subtext\">Save details commonly requested on forms.</p>
      <form method=\"POST\" action=\"/preferences/application\">\n        <input type=\"hidden\" id=\"csrf_token\" name=\"csrf_token\" value=\\"{csrf_cookie}\\">\n
        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Legal Entity Name</label>\n            <input type=\"text\" name=\"legal_name\" value=\"{v('legal_name')}\" placeholder=\"Acme, LLC\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">DBA</label>\n            <input type=\"text\" name=\"dba\" value=\"{v('dba')}\" placeholder=\"Acme Services\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">EIN / Tax ID</label>\n            <input type=\"text\" name=\"ein\" value=\"{v('ein')}\" placeholder=\"12-3456789\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">UEI / CAGE (optional)</label>\n            <input type=\"text\" name=\"uei\" value=\"{v('uei')}\" placeholder=\"UEI or CAGE Code\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Primary Contact Name</label>\n            <input type=\"text\" name=\"contact_name\" value=\"{v('contact_name')}\" placeholder=\"Jane Smith\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Title</label>\n            <input type=\"text\" name=\"contact_title\" value=\"{v('contact_title')}\" placeholder=\"Director\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Email</label>\n            <input type=\"email\" name=\"contact_email\" value=\"{v('contact_email', user_email or '')}\" placeholder=\"you@company.com\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Phone</label>\n            <input type=\"text\" name=\"contact_phone\" value=\"{v('contact_phone')}\" placeholder=\"(555) 555-5555\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Website</label>\n            <input type=\"text\" name=\"website\" value=\"{v('website')}\" placeholder=\"https://example.com\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Years in Business</label>\n            <input type=\"number\" name=\"years_in_business\" value=\"{v('years_in_business')}\" placeholder=\"10\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Business Type</label>\n            <input type=\"text\" name=\"business_type\" value=\"{v('business_type')}\" placeholder=\"LLC / S-Corp / Sole Prop\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">State of Incorporation</label>\n            <input type=\"text\" name=\"state_incorp\" value=\"{v('state_incorp')}\" placeholder=\"Ohio\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Physical Address</label>\n            <input type=\"text\" name=\"address\" value=\"{v('address')}\" placeholder=\"123 Main St, City, ST 00000\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Mailing Address</label>\n            <input type=\"text\" name=\"mailing_address\" value=\"{v('mailing_address')}\" placeholder=\"PO Box...\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Certifications</label>\n            <input type=\"text\" name=\"certifications\" value=\"{v('certifications')}\" placeholder=\"MBE, WBE, DBE, EDGE\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">NAICS / NIGP Codes</label>\n            <input type=\"text\" name=\"codes\" value=\"{v('codes')}\" placeholder=\"541611; 918-75\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Insurance Coverage Summary</label>\n            <input type=\"text\" name=\"insurance\" value=\"{v('insurance')}\" placeholder=\"GL $1M, Auto $1M, WC Statutory\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Bonding Capacity</label>\n            <input type=\"text\" name=\"bonding\" value=\"{v('bonding')}\" placeholder=\"$500k single / $1M aggregate\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Authorized Signatory</label>\n            <input type=\"text\" name=\"signatory\" value=\"{v('signatory')}\" placeholder=\"Name, Title\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Bank Reference (optional)</label>\n            <input type=\"text\" name=\"bank_ref\" value=\"{v('bank_ref')}\" placeholder=\"Bank, Contact, Phone\" />\n          </div>\n        </div>

        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Notes</label>\n            <input type=\"text\" name=\"notes\" value=\"{v('notes')}\" placeholder=\"Any special instructions or ids\" />\n          </div>\n        </div>

        <div class=\"form-actions\">\n          <button class=\"button-primary\" type=\"submit\">Save</button>\n          <span class=\"muted small\" style=\"margin-left:12px;\">Last saved: {updated_label or '-'}</span>\n        </div>\n      </form>

      <script>
        (function(){{
          try {{
            var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
            var t = m && m[1] ? decodeURIComponent(m[1]) : '';
            var i = document.getElementById('csrf_token');
            if (i && !i.value) i.value = t;
          }} catch(_) {{}}
        }})();
      </script>
    </section>
    """
    resp = HTMLResponse(
        page_shell(body_html, title="Application Variables", user_email=user_email),
        headers=cache_headers,
    )
    try:
        resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax")
    except Exception:
        pass
    return resp


@router.post("/preferences/application", response_class=HTMLResponse)
async def application_vars_save(request: Request):
    user_email = get_current_user_email(request)
    cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, private"}
    if not user_email:
        body = """
        <section class=\"card\">\n  <h2 class=\"section-heading\">Sign in required</h2>\n  <p class=\"subtext\">Please log in and resubmit.</p>\n  <a class=\"button-primary\" href=\"/login?next=/preferences/application\">Sign in</a>\n</section>
        """
        return HTMLResponse(
            page_shell(body, title="Application Variables", user_email=None),
            status_code=403,
            headers=cache_headers,
        )

    # Prefer raw body parse to avoid any body-consumption by middleware
    ctype = request.headers.get('content-type', '')
    raw = await request.body()
    parsed = {}
    try:
        if 'application/x-www-form-urlencoded' in ctype and raw:
            parsed = {k: v for k, v in parse_qs(raw.decode(errors='ignore')).items()}
    except Exception:
        parsed = {}
    if not parsed:
        try:
            _form = await request.form()
            parsed = {k: [_form.get(k)] for k in _form.keys()}
        except Exception:
            parsed = {}
    # No debug prints in production
    def g(name: str) -> str:
        try:
            val = parsed.get(name)
            if isinstance(val, list):
                return (val[0] or "").strip()
            return (val or "").strip()
        except Exception:
            return ""
    payload = {
        "legal_name": g("legal_name"),
        "dba": g("dba"),
        "ein": g("ein"),
        "uei": g("uei"),
        "contact_name": g("contact_name"),
        "contact_title": g("contact_title"),
        "contact_email": g("contact_email"),
        "contact_phone": g("contact_phone"),
        "website": g("website"),
        "years_in_business": g("years_in_business"),
        "business_type": g("business_type"),
        "state_incorp": g("state_incorp"),
        "address": g("address"),
        "mailing_address": g("mailing_address"),
        "certifications": g("certifications"),
        "codes": g("codes"),
        "insurance": g("insurance"),
        "bonding": g("bonding"),
        "signatory": g("signatory"),
        "bank_ref": g("bank_ref"),
        "notes": g("notes"),
    }

    async with AsyncSessionLocal() as session:
        # Load current to avoid overwriting with blanks
        current = {}
        cur_res = await session.execute(
            text("SELECT data FROM user_application_vars WHERE user_email = :email LIMIT 1"),
            {"email": user_email},
        )
        cur_row = cur_res.fetchone()
        if cur_row and cur_row[0] is not None:
            try:
                val = cur_row[0]
                if isinstance(val, dict):
                    current = val
                elif isinstance(val, (str, bytes)):
                    s = val.decode() if isinstance(val, bytes) else val
                    current = json.loads(s) if s else {}
            except Exception:
                current = {}

        # Merge: keep prior non-empty values when new are blank
        merged = {}
        for k in payload.keys():
            nv = (payload.get(k) or "").strip()
            pv = (current.get(k) if isinstance(current, dict) else None) or ""
            merged[k] = nv if nv else pv

        # Basic validation
        errors: list[str] = []
        # Require legal name and contact email after merge
        if not (merged.get("legal_name") or "").strip():
            errors.append("Legal entity name is required.")
        email_val = (merged.get("contact_email") or "").strip()
        if not email_val:
            errors.append("Contact email is required.")
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_val):
            errors.append("Contact email looks invalid.")
        # Optional numeric: years_in_business
        y = (merged.get("years_in_business") or "").strip()
        if y:
            if not y.isdigit():
                errors.append("Years in business must be a whole number.")
            else:
                yi = int(y)
                if yi < 0 or yi > 200:
                    errors.append("Years in business must be between 0 and 200.")
        # Optional EIN pattern
        einv = (merged.get("ein") or "").strip()
        if einv and not re.match(r"^\d{2}-?\d{7}$", einv):
            errors.append("EIN should look like 12-3456789.")
        # Optional website heuristic
        web = (merged.get("website") or "").strip()
        if web and not (web.startswith("http://") or web.startswith("https://") or "." in web):
            errors.append("Website should be a full URL (https://...) or a domain.")

        if errors:
            # Render form with posted values and an error banner
            def vv(key, default=""):
                try:
                    v = (payload.get(key) or "").strip()
                    return v if v != "" else (current.get(key) if isinstance(current, dict) else default) or default
                except Exception:
                    return default
            csrf_cookie = request.cookies.get("csrftoken") or secrets.token_urlsafe(32)
            alert = "<div style='background:#FEF2F2;border:1px solid #FECACA;color:#B91C1C;padding:10px 12px;border-radius:8px;margin-bottom:12px;'><b>Please fix and resubmit:</b><ul style='margin:6px 0 0 18px;'>" + "".join(f"<li>{e}</li>" for e in errors) + "</ul></div>"
            body_html = f"""
    <section class=\"card\">\n      <h2 class=\"section-heading\">Application Variables</h2>\n      <p class=\"subtext\">These details are commonly requested across applications. Keep them up to date.</p>\n      {alert}\n      <form method=\"POST\" action=\"/preferences/application\">\n        <input type=\"hidden\" id=\"csrf_token\" name=\"csrf_token\" value=\\"{csrf_cookie}\\">\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Legal Entity Name</label>\n            <input type=\"text\" name=\"legal_name\" value=\"{vv('legal_name')}\" placeholder=\"Acme, LLC\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">DBA</label>\n            <input type=\"text\" name=\"dba\" value=\"{vv('dba')}\" placeholder=\"Acme Services\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">EIN / Tax ID</label>\n            <input type=\"text\" name=\"ein\" value=\"{vv('ein')}\" placeholder=\"12-3456789\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">UEI / CAGE (optional)</label>\n            <input type=\"text\" name=\"uei\" value=\"{vv('uei')}\" placeholder=\"UEI or CAGE Code\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Primary Contact Name</label>\n            <input type=\"text\" name=\"contact_name\" value=\"{vv('contact_name')}\" placeholder=\"Jane Smith\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Title</label>\n            <input type=\"text\" name=\"contact_title\" value=\"{vv('contact_title')}\" placeholder=\"Director\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Email</label>\n            <input type=\"email\" name=\"contact_email\" value=\"{vv('contact_email')}\" placeholder=\"you@company.com\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Phone</label>\n            <input type=\"text\" name=\"contact_phone\" value=\"{vv('contact_phone')}\" placeholder=\"(555) 555-5555\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Website</label>\n            <input type=\"text\" name=\"website\" value=\"{vv('website')}\" placeholder=\"https://example.com\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Years in Business</label>\n            <input type=\"number\" name=\"years_in_business\" value=\"{vv('years_in_business')}\" placeholder=\"10\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Business Type</label>\n            <input type=\"text\" name=\"business_type\" value=\"{vv('business_type')}\" placeholder=\"LLC / S-Corp / Sole Prop\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">State of Incorporation</label>\n            <input type=\"text\" name=\"state_incorp\" value=\"{vv('state_incorp')}\" placeholder=\"Ohio\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Physical Address</label>\n            <input type=\"text\" name=\"address\" value=\"{vv('address')}\" placeholder=\"123 Main St, City, ST 00000\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Mailing Address</label>\n            <input type=\"text\" name=\"mailing_address\" value=\"{vv('mailing_address')}\" placeholder=\"PO Box...\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Certifications</label>\n            <input type=\"text\" name=\"certifications\" value=\"{vv('certifications')}\" placeholder=\"MBE, WBE, DBE, EDGE\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">NAICS / NIGP Codes</label>\n            <input type=\"text\" name=\"codes\" value=\"{vv('codes')}\" placeholder=\"541611; 918-75\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Insurance Coverage Summary</label>\n            <input type=\"text\" name=\"insurance\" value=\"{vv('insurance')}\" placeholder=\"GL $1M, Auto $1M, WC Statutory\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Bonding Capacity</label>\n            <input type=\"text\" name=\"bonding\" value=\"{vv('bonding')}\" placeholder=\"$500k single / $1M aggregate\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Authorized Signatory</label>\n            <input type=\"text\" name=\"signatory\" value=\"{vv('signatory')}\" placeholder=\"Name, Title\" />\n          </div>\n          <div class=\"form-col\">\n            <label class=\"label-small\">Bank Reference (optional)</label>\n            <input type=\"text\" name=\"bank_ref\" value=\"{vv('bank_ref')}\" placeholder=\"Bank, Contact, Phone\" />\n          </div>\n        </div>\n\n        <div class=\"form-row\">\n          <div class=\"form-col\">\n            <label class=\"label-small\">Notes</label>\n            <input type=\"text\" name=\"notes\" value=\"{vv('notes')}\" placeholder=\"Any special instructions or ids\" />\n          </div>\n        </div>\n\n        <div class=\"form-actions\">\n          <button class=\"button-primary\" type=\"submit\">Save</button>\n          <span class=\"muted small\" style=\"margin-left:12px;\">Last saved: -</span>\n        </div>\n      </form>\n    </section>\n            """
            resp = HTMLResponse(
                page_shell(body_html, title="Application Variables", user_email=user_email),
                status_code=400,
                headers=cache_headers,
            )
            try:
                resp.set_cookie("csrftoken", csrf_cookie, httponly=False, samesite="lax")
            except Exception:
                pass
            return resp

        params = {"email": user_email, "data": json.dumps(merged)}
        # No debug prints in production
        # Robust upsert compatible with SQLite: UPDATE first, then INSERT if needed
        upd = await session.execute(
            text(
                """
                UPDATE user_application_vars
                SET data = :data, updated_at = CURRENT_TIMESTAMP
                WHERE user_email = :email
                """
            ),
            params,
        )
        if getattr(upd, "rowcount", 0) == 0:
            await session.execute(
                text(
                    """
                    INSERT INTO user_application_vars (user_email, data)
                    VALUES (:email, :data)
                    """
                ),
                params,
            )
        await session.commit()

    # Redirect back to the form so the user sees their saved values and updated timestamp
    return RedirectResponse(url="/preferences/application", status_code=303)


# Lightweight API endpoint for AI/autofill integrations
@router.get("/api/me/application_vars")
async def get_my_application_vars(request: Request):
    user_email = get_current_user_email(request)
    if not user_email:
        return {"ok": False, "error": "not_authenticated"}
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT data FROM user_application_vars WHERE user_email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        out = {}
        if row and row[0] is not None:
            try:
                out = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            except Exception:
                out = {}
    return {"ok": True, "data": out}








