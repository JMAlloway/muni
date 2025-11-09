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
