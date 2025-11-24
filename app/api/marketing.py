# app/routers/marketing.py
import datetime as dt
import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api._layout import page_shell
from app.auth.session import get_current_user_email
from app.services.opportunity_feed import fetch_landing_snapshot

router = APIRouter(tags=["marketing"])


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_email = get_current_user_email(request)
    stats, preview_rows = await fetch_landing_snapshot()

    def format_due(value) -> str:
        if not value:
            return "TBD"
        if isinstance(value, str):
            try:
                parsed = dt.datetime.fromisoformat(value)
            except ValueError:
                return value
        else:
            parsed = value
        return parsed.strftime("%b %d")

    preview_cards = "".join(
        f"""
        <div class="preview-card">
            <div class="mini-head">{html.escape(row.get("agency_name") or "Agency")}</div>
            <div class="blurred-text">{html.escape(row.get("title") or "Live opportunity")}</div>
            <div class="muted">Due {format_due(row.get("due_date"))}</div>
        </div>
        """
        for row in preview_rows
    )

    hero = f"""
    <section class="card reveal hero-gradient" style="text-align:center;">
        <div class="hero-brand">
            <img src="static/logo.svg" alt="EasyRFP logo" class="brand-logo brand-logo-hero" />
            <div class="brand-tagline">EasyRFP &middot; Central Ohio pilot</div>
        </div>
        <div class="pill" style="display:inline-block;margin-bottom:10px;">Central Ohio Pilot  &middot;  Early Access</div>
        <h1 class="section-heading" style="font-size:34px;margin-bottom:12px;letter-spacing:-0.03em;">Stop checking 21 city sites—let us watch them for you</h1>
        <p class="subtext" style="font-size:15px;margin:0 auto 20px;max-width:720px;">
            Save 10+ hours a week hunting bids. EasyRFP monitors municipal portals, summarizes every opportunity, and alerts you before deadlines so you can spend time drafting proposals—not refreshing websites. Teams that catch opportunities early win more work.
        </p>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
          <a class="button-primary" href="/signup">Start free</a>
          <a class="cta-link" href="/opportunities">Preview live opportunities</a>
        </div>
        <div class="muted" style="margin-top:8px;">No credit card  &middot;  Takes 90 seconds to set up</div>
    </section>
    """

    live_section = f"""
    <section class="card">
                <div class="head-row" style="align-items:flex-start;">
            <div>
                <h2 class="section-heading">Live snapshot</h2>
                <div class="mini-desc">Updated automatically every few hours.</div>
            </div>
            <div style="margin-left:auto;">
                <a class="button-primary" href="/signup">Reveal details</a>
            </div>
        </div>
        <div class="stat-row" style="margin-top:12px;">
            <div class="stat"><b>{stats["total_open"]}</b><span class="muted">Open opportunities</span></div>
            <div class="stat"><b>{stats["closing_soon"]}</b><span class="muted">Closing in 7 days</span></div>
            <div class="stat"><b>{stats["added_recent"]}</b><span class="muted">Added last 24 hrs</span></div>
        </div>
        <div class="preview-grid">
            {preview_cards or "<div class='muted'>Fresh opportunities are populating...</div>"}
        </div>
        <div class="muted" style="margin-top:10px;">Unlock full titles, summaries, and documents with a free account.</div>
    </section>
    """

    audience = """
    <section class="card">
        <h2 class="section-heading">Why teams choose EasyRFP</h2>
        <div class="flex-grid">
            <div>
                <div class="mini-head">Skip the scavenger hunt</div>
                <div class="mini-desc">Live local bids with plain-language summaries, source links, and due dates.</div>
            </div>
            <div>
                <div class="mini-head">Stay ahead of deadlines</div>
                <div class="mini-desc">Due-soon highlights and reminders keep important dates from slipping.</div>
            </div>
            <div>
                <div class="mini-head">Track with one click</div>
                <div class="mini-desc">Save an opportunity, add a status, and share notesâ€”everything lives in your dashboard.</div>
            </div>
        </div>
    </section>
    """

    how = """
    <section class="card">
        <h2 class="section-heading">Try it in minutes</h2>
        <div class="flex-grid">
            <div>
                <div class="mini-head">1) Tell us what you buy</div>
                <div class="mini-desc">Pick a focus and we tailor the feed instantly.</div>
            </div>
            <div>
                <div class="mini-head">2) Track your first bid</div>
                <div class="mini-desc">Hit “Track” to unlock alerts, uploads, and team notes.</div>
            </div>
            <div>
                <div class="mini-head">3) Get nudges, not noise</div>
                <div class="mini-desc">Morning snapshots and due reminders keep you on pace without spam.</div>
            </div>
        </div>
    </section>
    """

    coverage = """
    <section class="card">
        <h2 class="section-heading">Coverage</h2>
        <p class="subtext">Pilot focus on Central Ohio with expanding agencies.</p>
        <div class="flex-grid">
            <div><span class="pill">City of Columbus</span></div>
            <div><span class="pill">COTA</span></div>
            <div><span class="pill">SWACO</span></div>
            <div><span class="pill">CRAA</span></div>
            <div><span class="pill">Gahanna</span></div>
            <div><span class="pill">Delaware County</span></div>
        </div>
        <div class="logo-row" style="margin-top:10px;">
            <img class="logo" alt="Columbus" src="/static/columbus.png" onerror="this.style.display='none'">
            <img class="logo" alt="Agency" src="/static/logo.svg" onerror="this.style.display='none'">
            <img class="logo" alt="Agency" src="/static/logo.svg" onerror="this.style.display='none'">
            <img class="logo" alt="Agency" src="/static/logo.svg" onerror="this.style.display='none'">
        </div>
    </section>
    """

    pricing = """
    <section class="card">
        <h2 class="section-heading">Plans built for contractors</h2>
        <p class="subtext">Start free, upgrade when you need realtime alerts and team tools.</p>
        <div class="flex-grid" style="align-items:stretch;">
            <div class="card" style="border:1px solid #e5e7eb; box-shadow:none; margin:0; padding:16px;">
                <div class="mini-head">Free</div>
                <div class="mini-desc" style="margin-bottom:8px;">Lead funnel for small teams</div>
                <div style="font-size:22px;font-weight:700;">$0</div>
                <ul class="features">
                    <li>View opportunities (24h delay)</li>
                    <li>Track up to 3 bids</li>
                    <li>Weekly digest emails</li>
                </ul>
            </div>
            <div class="card" style="border:1px solid #c7d2fe; box-shadow:none; margin:0; padding:16px;">
                <div class="mini-head">Starter</div>
                <div class="mini-desc" style="margin-bottom:8px;">For owners and solo PMs</div>
                <div style="font-size:22px;font-weight:700;">$29/mo</div>
                <ul class="features">
                    <li>Realtime updates</li>
                    <li>Track unlimited bids</li>
                    <li>Daily digests and keyword alerts</li>
                    <li>File uploads (5 GB)</li>
                </ul>
            </div>
            <div class="card" style="border:1px solid #e5e7eb; box-shadow:none; margin:0; padding:16px;">
                <div class="mini-head">Professional</div>
                <div class="mini-desc" style="margin-bottom:8px;">For teams that bid often</div>
                <div style="font-size:22px;font-weight:700;">$99/mo</div>
                <ul class="features">
                    <li>Everything in Starter</li>
                    <li>AI bid matching</li>
                    <li>Proposal templates</li>
                    <li>Team collaboration (3 users)</li>
                    <li>Priority support</li>
                </ul>
            </div>
            <div class="card" style="border:1px solid #e5e7eb; box-shadow:none; margin:0; padding:16px;">
                <div class="mini-head">Enterprise</div>
                <div class="mini-desc" style="margin-bottom:8px;">For multi-office contractors</div>
                <div style="font-size:22px;font-weight:700;">$299/mo</div>
                <ul class="features">
                    <li>Everything in Professional</li>
                    <li>Unlimited team members</li>
                    <li>Custom agency coverage</li>
                    <li>API access</li>
                    <li>Win/loss analytics</li>
                </ul>
            </div>
        </div>
    </section>
    """

    preview = """
    <section class="card">
        <h2 class="section-heading">Welcome dashboard preview</h2>
        <div class="mini-desc">After signup you land on a curated list with Track buttons, AI summaries, and due badges.</div>
        <div class="table-wrap" style="margin-top:10px;">
            <table>
                <thead><tr><th>Title</th><th>Agency</th><th>Due</th><th>Category</th></tr></thead>
                <tbody>
                    <tr><td>On-call sidewalk repairs</td><td>City of Columbus</td><td>Mar 12</td><td>Construction</td></tr>
                    <tr><td>IT service desk support</td><td>COTA</td><td>Mar 18</td><td>Information Technology</td></tr>
                    <tr><td>Creative design services</td><td>Gahanna</td><td>Mar 22</td><td>Professional Services</td></tr>
                </tbody>
            </table>
        </div>
        <div style="margin-top:12px;"><a class="cta-link" href="/opportunities">See the live feed</a></div>
    </section>
    """

    email_sample = """
    <section class="card">
        <h2 class="section-heading">Email updates you'll actually read</h2>
        <div class="mini-desc">A quick morning summary with new and due-soon items.</div>
        <div style="font-size:13px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin-top:10px;">
            <div><b>New today</b></div>
            <div>- City of Columbus &mdash; Snow removal equipment lease (Apr 2)</div>
            <div>- COTA &mdash; Network switches replacement (Mar 28)</div>
            <div style="margin-top:8px;"><b>Due soon</b></div>
            <div>- Gahanna &mdash; Parks mowing services (Mar 14)</div>
        </div>
    </section>
    """

    closer = """
    <section class="card" style="text-align:center;">
        <h2 class="section-heading">Ready to try it?</h2>
        <p class="subtext">Create a free account, pick an interest, and start tracking bids.</p>
        <a class="button-primary" href="/signup">Get Started</a>
    </section>
    """

    body_html = hero + live_section + audience + how + pricing + coverage + preview + email_sample + closer
    return HTMLResponse(page_shell(body_html, title="EasyRFP  &middot;  Win Local Bids Faster", user_email=user_email))


@router.get("/landing-test", response_class=HTMLResponse)
async def landing_test(request: Request):
    user_email = get_current_user_email(request)
    body_html = """
    <section class="card" style="text-align:center;">
        <h2 class="section-heading">Simple landing test</h2>
        <p class="subtext">This is a lightweight preview route kept for development.</p>
        <a class="button-primary" href="/signup">Try it free</a>
    </section>
    """
    return HTMLResponse(page_shell(body_html, title="EasyRFP  &middot;  Preview", user_email=user_email))

