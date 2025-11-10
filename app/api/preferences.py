# app/routers/preferences.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from typing import List
import json

from app.core.db import AsyncSessionLocal
from app.api._layout import page_shell
from app.auth.session import get_current_user_email

router = APIRouter(tags=["preferences"])

@router.get("/preferences", response_class=HTMLResponse)
async def get_preferences(request: Request):
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

    return HTMLResponse(page_shell(body_html, title="Muni Alerts – Preferences", user_email=user_email))


@router.post("/preferences", response_class=HTMLResponse)
async def post_preferences(
    request: Request,
    email: str = Form(...),
    frequency: str = Form(...),
    agency: List[str] = Form([]),
):
    user_email = get_current_user_email(request)

    email_clean = email.strip().lower()
    freq_clean = frequency.strip().lower()
    if freq_clean not in ("daily", "weekly", "none"):
        freq_clean = "daily"

    agencies_json = json.dumps(agency)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO users (email, digest_frequency, agency_filter, created_at)
                VALUES (:email, :freq, :agencies, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    digest_frequency = excluded.digest_frequency,
                    agency_filter = excluded.agency_filter
            """),
            {
                "email": email_clean,
                "freq": freq_clean,
                "agencies": agencies_json,
            },
        )
        await session.commit()

    agencies_label = ", ".join(agency) if agency else "All"

    body_html = f"""
    <section class="card">
        <h2 class="section-heading">You're on the list ✅</h2>
        <p class="subtext" style="margin-bottom:16px;">
            We'll send opportunities to <b>{email_clean}</b> at <b>{freq_clean}</b> frequency.
        </p>

        <div class="mini-head" style="margin-bottom:4px;">Agencies selected</div>
        <div class="mini-desc" style="margin-bottom:16px;">
            <code class="chip">{agencies_label}</code>
        </div>

        <a class="button-primary" href="/opportunities">See current bids →</a>
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
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT data FROM user_application_vars WHERE user_email = :email LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if row and row[0]:
            try:
                data = row[0]
            except Exception:
                data = {}

    def v(key, default=""):
        try:
            return (data or {}).get(key) or default
        except Exception:
            return default

    body_html = f"""
    <section class=\"card\">
      <h2 class=\"section-heading\">Application Variables</h2>
      <p class=\"subtext\">Save details commonly requested on forms.</p>
      <form method=\"POST\" action=\"/preferences/application\">\n        <input type=\"hidden\" id=\"csrf_token\" name=\"csrf_token\" value=\"\">\n
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

        <div class=\"form-actions\">\n          <button class=\"button-primary\" type=\"submit\">Save</button>\n        </div>\n      </form>

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
    return HTMLResponse(page_shell(body_html, title="Application Variables", user_email=user_email))


@router.post("/preferences/application", response_class=HTMLResponse)
async def application_vars_save(
    request: Request,
    legal_name: str = Form(""),
    dba: str = Form(""),
    ein: str = Form(""),
    uei: str = Form(""),
    contact_name: str = Form(""),
    contact_title: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    website: str = Form(""),
    years_in_business: str = Form(""),
    business_type: str = Form(""),
    state_incorp: str = Form(""),
    address: str = Form(""),
    mailing_address: str = Form(""),
    certifications: str = Form(""),
    codes: str = Form(""),
    insurance: str = Form(""),
    bonding: str = Form(""),
    signatory: str = Form(""),
    bank_ref: str = Form(""),
    notes: str = Form(""),
):
    user_email = get_current_user_email(request)
    if not user_email:
        body = """
        <section class=\"card\">\n  <h2 class=\"section-heading\">Sign in required</h2>\n  <p class=\"subtext\">Please log in and resubmit.</p>\n  <a class=\"button-primary\" href=\"/login?next=/preferences/application\">Sign in</a>\n</section>
        """
        return HTMLResponse(page_shell(body, title="Application Variables", user_email=None), status_code=403)

    payload = {
        "legal_name": (legal_name or "").strip(),
        "dba": (dba or "").strip(),
        "ein": (ein or "").strip(),
        "uei": (uei or "").strip(),
        "contact_name": (contact_name or "").strip(),
        "contact_title": (contact_title or "").strip(),
        "contact_email": (contact_email or "").strip(),
        "contact_phone": (contact_phone or "").strip(),
        "website": (website or "").strip(),
        "years_in_business": (years_in_business or "").strip(),
        "business_type": (business_type or "").strip(),
        "state_incorp": (state_incorp or "").strip(),
        "address": (address or "").strip(),
        "mailing_address": (mailing_address or "").strip(),
        "certifications": (certifications or "").strip(),
        "codes": (codes or "").strip(),
        "insurance": (insurance or "").strip(),
        "bonding": (bonding or "").strip(),
        "signatory": (signatory or "").strip(),
        "bank_ref": (bank_ref or "").strip(),
        "notes": (notes or "").strip(),
    }

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO user_application_vars (user_email, data)
                VALUES (:email, :data)
                ON CONFLICT(user_email) DO UPDATE SET
                  data = excluded.data,
                  updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"email": user_email, "data": json.dumps(payload)},
        )
        await session.commit()

    body = """
    <section class=\"card\">\n  <h2 class=\"section-heading\">Saved</h2>\n  <p class=\"subtext\">Your application variables have been saved.</p>\n  <a class=\"button-primary\" href=\"/preferences/application\">Go back</a>\n</section>
    """
    return HTMLResponse(page_shell(body, title="Application Variables", user_email=user_email))
