# app/routers/marketing.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.routers._layout import page_shell
from app.session import get_current_user_email

router = APIRouter(tags=["marketing"])


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_email = get_current_user_email(request)

    hero = """
    <section class="card reveal" style="text-align:center;">
        <h1 class="section-heading" style="font-size:28px;margin-bottom:12px;">
            Stop missing city RFPs and bids.
        </h1>
        <p class="subtext" style="font-size:15px;margin-bottom:20px;">
            Muni Alerts monitors Central Ohio municipal procurement portals, normalizes bid data, and
            emails you new opportunities before deadlines hit.
        </p>
        <a class="button-primary" href="/signup">Get Started Free →</a>
        <div class="muted" style="margin-top:8px;">No credit card required.</div>
    </section>
    """

    why = """
    <section class="card">
        <h2 class="section-heading">Why Muni Alerts?</h2>
        <div class="flex-grid">
            <div>
                <div class="mini-head">⚡ Speed</div>
                <div class="mini-desc">We scrape every local portal multiple times per day — you get alerts within hours of posting.</div>
            </div>
            <div>
                <div class="mini-head">🎯 Focus</div>
                <div class="mini-desc">We focus on Central Ohio municipalities, giving you signal, not national noise.</div>
            </div>
            <div>
                <div class="mini-head">🧠 Smart Tracking</div>
                <div class="mini-desc">We normalize titles, due dates, and agency names so you can browse or filter consistently.</div>
            </div>
            <div>
                <div class="mini-head">📬 Automated Alerts</div>
                <div class="mini-desc">Daily or weekly email summaries tailored to your agency preferences.</div>
            </div>
        </div>
    </section>
    """

    # NEW: internal / ops view – reflects latest stuff we added
    internal_overview = """
    <section class="card" style="border:1px solid rgba(249,115,22,0.25);">
        <div style="display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap;">
            <div style="flex:1 1 260px;min-width:240px;">
                <h2 class="section-heading" style="display:flex;align-items:center;gap:6px;">
                    <span>System overview (internal)</span>
                    <span style="
                        background:rgba(16,185,129,0.12);
                        color:#047857;
                        font-size:11px;
                        padding:2px 8px;
                        border-radius:12px;
                        border:1px solid rgba(4,120,87,0.35);
                    ">2025</span>
                </h2>
                <p class="subtext">
                    This instance is now set up for local ingest + Heroku web, with AI category, source-link fallbacks, and email digests.
                </p>
            </div>
            <div style="flex:2 1 380px;min-width:260px;">
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;">
                    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:10px 12px;">
                        <div style="font-size:12px;font-weight:600;color:#c2410c;margin-bottom:4px;">AI & categories</div>
                        <div style="font-size:12px;color:#7c2d12;line-height:1.45;">
                            <strong>ai_category</strong> now saved on <code>opportunities</code>.
                            Rule-first, LLM fallback (Ollama local → OpenAI on Heroku).
                        </div>
                    </div>
                    <div style="background:#eff6ff;border:1px solid #dbeafe;border-radius:12px;padding:10px 12px;">
                        <div style="font-size:12px;font-weight:600;color:#1d4ed8;margin-bottom:4px;">Source link fallback</div>
                        <div style="font-size:12px;color:#1e40af;line-height:1.45;">
                            COTA / Columbus now point to an agency-level page when scraped URL is blank or JS-only.
                        </div>
                    </div>
                    <div style="background:#ecfdf3;border:1px solid #bbf7d0;border-radius:12px;padding:10px 12px;">
                        <div style="font-size:12px;font-weight:600;color:#15803d;margin-bottom:4px;">Heroku split</div>
                        <div style="font-size:12px;color:#166534;line-height:1.45;">
                            Web dyno: FastAPI only. Worker dyno: <code>ingest.runner</code> + digests.
                        </div>
                    </div>
                    <div style="background:#f3e8ff;border:1px solid #e9d5ff;border-radius:12px;padding:10px 12px;">
                        <div style="font-size:12px;font-weight:600;color:#6b21a8;margin-bottom:4px;">Email digests</div>
                        <div style="font-size:12px;color:#581c87;line-height:1.45;">
                            Uses Mailtrap SMTP; respects user agency filters. Good for pilot.
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div style="margin-top:14px;">
            <h3 style="font-size:13px;font-weight:600;margin-bottom:4px;">Current coverage</h3>
            <p style="font-size:12px;line-height:1.45;color:#374151;">
                City of Columbus, City of Gahanna, City of Grove City, City of Marysville, City of Whitehall,
                City of Grandview Heights, City of Worthington, Delaware County, SWACO,
                Central Ohio Transit Authority (COTA), Columbus Regional Airport Authority (CRAA),
                Mid-Ohio Regional Planning Commission (MORPC), Columbus & Franklin County Metro Parks,
                Columbus Metropolitan Library, Dublin City Schools, Westerville (Bonfire).
            </p>
        </div>

        <div style="margin-top:10px;font-size:11px;color:#6b7280;">
            Reminder: on Heroku we must create both ORM tables AND core <code>opportunities</code> on startup.
        </div>
    </section>
    """

    pricing = """
    <section class="card" style="text-align:center;">
        <h2 class="section-heading">Simple, transparent pricing</h2>
        <p class="subtext" style="margin-bottom:24px;">Start free. Upgrade when you need multi-user alerts or extra regions.</p>
        <div class="flex-grid" style="justify-content:center;">
            <div class="card" style="max-width:260px;margin:auto;">
                <div class="mini-head">Free Tier</div>
                <div class="mini-desc">1 user, 2 agencies, daily alerts</div>
                <div style="font-size:24px;font-weight:700;margin:8px 0;">$0</div>
                <a href="/signup" class="button-primary">Sign Up Free</a>
            </div>
            <div class="card" style="max-width:260px;margin:auto;">
                <div class="mini-head">Pro Tier</div>
                <div class="mini-desc">Up to 10 agencies, team alerts, weekly digest export</div>
                <div style="font-size:24px;font-weight:700;margin:8px 0;">$29/mo</div>
                <a href="/signup" class="button-primary">Start Trial</a>
            </div>
        </div>
    </section>
    """

    trust = """
    <section class="card">
        <h2 class="section-heading">Who uses Muni Alerts?</h2>
        <p class="subtext">
            Local contractors, IT service firms, marketing agencies, and community vendors who
            need a steady feed of government bid opportunities without checking every portal manually.
        </p>
        <ul style="margin:12px 0 0 18px;padding:0;font-size:13px;color:#374151;line-height:1.4;">
            <li>Construction and trades (plumbing, paving, HVAC, etc.)</li>
            <li>Consultants and design firms bidding on RFPs</li>
            <li>Suppliers and distributors selling to cities</li>
            <li>Financial institutions tracking local contracts</li>
        </ul>
    </section>
    """

    footer = """
    <section class="card" style="text-align:center;">
        <p class="muted">
            Built in Ohio • v0.3 Alpha • <a href="/signup" class="cta-link">Create Account</a>
        </p>
    </section>
    """

    body_html = hero + why + internal_overview + pricing + trust + footer
    return HTMLResponse(page_shell(body_html, title="Muni Alerts – Stop Missing Local Bids", user_email=user_email))


@router.get("/landing-test", response_class=HTMLResponse)
async def landing_test(request: Request):
    # KEEPING your existing test landing page as-is
    user_email = get_current_user_email(request)

    hero = """
    <section class="card reveal" style="
        text-align:center;
        background:radial-gradient(circle at 20% 20%, #eef2ff 0%, #ffffff 60%);
        border:1px solid var(--pill-border);
    ">
        <div style="
            display:inline-block;
            margin-bottom:12px;
            background:var(--pill-bg);
            border:1px solid var(--pill-border);
            color:var(--pill-text);
            font-size:12px;
            font-weight:500;
            line-height:1.2;
            padding:4px 10px;
            border-radius:var(--radius-pill);
        ">
            Central Ohio Pilot • Early Access
        </div>

        <h1 class="section-heading" style="
            font-size:30px;
            line-height:1.15;
            letter-spacing:-0.05em;
            margin-bottom:12px;
        ">
            Stop missing local government contracts.
        </h1>

        <p class="subtext" style="
            font-size:15px;
            line-height:1.5;
            max-width:520px;
            margin:0 auto 20px auto;
            color:#4b5563;
        ">
            We watch City of Columbus, Gahanna, Grove City, Delaware County and more — 
            and send you bids, deadlines, and documents straight to your inbox.
            No more portal-hopping.
        </p>

        <a class="button-primary" href="/signup" style="font-size:15px;padding:12px 16px;border-radius:10px;">
            Get bid alerts →
        </a>
        <div class="muted" style="margin-top:8px;font-size:12px;">
            No spam. Cancel anytime.
        </div>

        <div style="
            display:flex;
            flex-wrap:wrap;
            justify-content:center;
            gap:8px 12px;
            margin-top:24px;
        ">
            <div style="
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:var(--radius-pill);
                font-size:12px;
                padding:6px 10px;
                color:#374151;
                line-height:1.2;
                font-weight:500;
            ">Columbus Vendor Services</div>
            <div style="
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:var(--radius-pill);
                font-size:12px;
                padding:6px 10px;
                color:#374151;
                line-height:1.2;
                font-weight:500;
            ">Gahanna Bids & RFPs</div>
            <div style="
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:var(--radius-pill);
                font-size:12px;
                padding:6px 10px;
                color:#374151;
                line-height:1.2;
                font-weight:500;
            ">Grove City Procurement</div>
            <div style="
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:var(--radius-pill);
                font-size:12px;
                padding:6px 10px;
                color:#374151;
                line-height:1.2;
                font-weight:500;
            ">Delaware County</div>
        </div>
    </section>
    """

    audience = """
    <section class="card reveal" style="border:1px solid var(--border-card);">
        <div style="display:flex;flex-wrap:wrap;row-gap:16px;column-gap:24px;align-items:flex-start;">
            <div style="flex:1 1 240px;min-width:240px;">
                <div class="mini-head" style="font-size:13px;font-weight:600;color:var(--accent-text);margin-bottom:6px;">
                    BUILT FOR
                </div>
                <div style="font-size:20px;font-weight:600;line-height:1.2;letter-spacing:-0.03em;color:#111827;margin-bottom:8px;">
                    Local contractors and service providers
                </div>
                <div class="mini-desc" style="font-size:13px;color:#4b5563;max-width:460px;">
                    You don't have a full-time bid desk. You still want the work. We track new RFPs and bid postings for you — and email them in plain English.
                </div>
            </div>
            <div style="flex:1 1 220px;min-width:220px;">
                <ul style="margin:0;padding-left:18px;font-size:13px;color:#374151;line-height:1.45;">
                    <li>Asphalt / paving / concrete</li>
                    <li>HVAC, electrical, plumbing</li>
                    <li>IT & cabling / network services</li>
                    <li>Janitorial, grounds, tree work</li>
                    <li>Consulting & professional services</li>
                </ul>
            </div>
        </div>
    </section>
    """

    features = """
    <section class="card reveal">
        <h2 class="section-heading" style="margin-bottom:16px;">What you get</h2>

        <div class="flex-grid">
            <div style="position:relative;padding-left:28px;">
                <div style="
                    position:absolute;
                    left:0;
                    top:2px;
                    width:20px;
                    height:20px;
                    border-radius:6px;
                    background:var(--accent-bg);
                    color:#fff;
                    font-size:12px;
                    font-weight:600;
                    line-height:20px;
                    text-align:center;
                ">1</div>
                <div class="mini-head">Alerts on your schedule</div>
                <div class="mini-desc">
                    You pick daily or weekly alerts — we email you.
                    No dashboards you’ll forget to check.
                </div>
            </div>

            <div style="position:relative;padding-left:28px;">
                <div style="
                    position:absolute;
                    left:0;
                    top:2px;
                    width:20px;
                    height:20px;
                    border-radius:6px;
                    background:var(--accent-bg);
                    color:#fff;
                    font-size:12px;
                    font-weight:600;
                    line-height:20px;
                    text-align:center;
                ">2</div>
                <div class="mini-head">All cities in one feed</div>
                <div class="mini-desc">
                    Columbus, Gahanna, Grove City, Delaware County and more —
                    combined into one clean summary.
                </div>
            </div>

            <div style="position:relative;padding-left:28px;">
                <div style="
                    position:absolute;
                    left:0;
                    top:2px;
                    width:20px;
                    height:20px;
                    border-radius:6px;
                    background:var(--accent-bg);
                    color:#fff;
                    font-size:12px;
                    font-weight:600;
                    line-height:20px;
                    text-align:center;
                ">3</div>
                <div class="mini-head">Key info up front</div>
                <div class="mini-desc">
                    Pre-bid meetings, due dates, required attachments.
                    Know in 30 seconds if it's worth pursuing.
                </div>
            </div>
        </div>
    </section>
    """

    coverage = """
    <section class="card reveal">
        <h2 class="section-heading" style="margin-bottom:8px;">Currently monitoring</h2>
        <p class="subtext" style="margin-bottom:20px;">
            We’re focused on Central Ohio first. You get depth, not national noise.
        </p>

        <div style="
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));
            gap:12px 16px;
            font-size:13px;
            line-height:1.4;
            color:#111;
            font-weight:500;
        ">
            <div>✅ City of Columbus</div>
            <div>✅ City of Gahanna</div>
            <div>✅ City of Grove City</div>
            <div>✅ Delaware County</div>
            <div>➕ Franklin / Union / Licking County (in progress)</div>
        </div>

        <div class="muted" style="margin-top:16px;font-size:12px;line-height:1.4;">
            Want your city added next? <a class="cta-link" href="/signup">Tell us when you sign up</a>.
        </div>
    </section>
    """

    pricing = """
    <section class="card reveal" style="text-align:center;">
        <h2 class="section-heading" style="margin-bottom:8px;">Pricing</h2>
        <p class="subtext" style="font-size:14px;margin-bottom:24px;">
            Winning one job makes this basically free.
        </p>

        <div style="
            display:flex;
            flex-wrap:wrap;
            gap:16px;
            justify-content:center;
            text-align:left;
        ">

            <div class="card" style="
                max-width:260px;
                margin:auto;
                border:1px solid var(--border-card);
            ">
                <div class="mini-head">Starter</div>
                <div class="mini-desc">1 email, daily or weekly alerts for your city.</div>
                <div style="font-size:24px;font-weight:700;margin:8px 0;">$0</div>
                <div class="mini-desc" style="margin-bottom:12px;color:#4b5563;">
                    Get notified when new work is posted. Try it with zero risk.
                </div>
                <a href="/signup" class="button-primary" style="width:100%;text-align:center;">Get started →</a>
            </div>

            <div class="card" style="
                max-width:260px;
                margin:auto;
                border:1px solid var(--border-card);
            ">
                <div class="mini-head">Pro</div>
                <div class="mini-desc">Multiple cities, shared inbox, export.</div>
                <div style="font-size:24px;font-weight:700;margin:8px 0;">Coming soon</div>
                <div class="mini-desc" style="margin-bottom:12px;color:#4b5563;">
                    If one awarded job covers a crew for a week,
                    it already paid for itself.
                </div>
                <a href="/signup" class="button-primary" style="width:100%;text-align:center;">Join early list →</a>
            </div>
        </div>
    </section>
    """

    closer = """
    <section class="card reveal" style="
        text-align:center;
        background:#111827;
        color:#fff;
        border:1px solid #000;
    ">
        <div class="mini-head" style="color:#a5b4fc;font-size:12px;letter-spacing:-0.03em;margin-bottom:8px;">
            You’re early.
        </div>
        <div style="
            font-size:20px;
            font-weight:600;
            line-height:1.2;
            letter-spacing:-0.03em;
            margin-bottom:12px;
        ">
            We scan the portals.<br/>You get the work.
        </div>
        <a class="button-primary" href="/signup" style="
            background:var(--accent-bg);
            border:1px solid rgba(255,255,255,0.15);
            font-size:15px;
            padding:12px 16px;
            border-radius:10px;
            text-decoration:none;
        ">
            Get bid alerts →
        </a>
        <div class="muted" style="color:#9ca3af;margin-top:12px;font-size:12px;">
            Built in Ohio • Pilot in Central Ohio
        </div>
    </section>
    """

    body_html = hero + audience + features + coverage + pricing + closer

    return HTMLResponse(
        page_shell(
            body_html,
            title="Muni Alerts – Stop Missing Local Contracts",
            user_email=user_email,
        )
    )
