# app/routers/marketing.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.api._layout import page_shell
from app.auth.session import get_current_user_email

router = APIRouter(tags=["marketing"])


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_email = get_current_user_email(request)

    hero = """
    <section class=\"card reveal hero-gradient\" style=\"text-align:center;\">
        <div class=\"pill\" style=\"display:inline-block;margin-bottom:10px;\">Central Ohio Pilot • Early Access</div>
        <h1 class=\"section-heading\" style=\"font-size:32px;margin-bottom:10px;letter-spacing:-0.04em;\">EasyRFP helps you win local work</h1>
        <p class=\"subtext\" style=\"font-size:15px;margin:0 auto 18px;max-width:620px;\">
            EasyRFP aggregates open bids from Central Ohio cities and agencies and emails you clear, timely updates.
            Coming soon: a file hub and a guided bid tracker so you never miss a step.
        </p>
        <div style=\"display:flex;gap:10px;justify-content:center;flex-wrap:wrap;\">
          <a class=\"button-primary\" href=\"/signup\">Start Free</a>
          <a class=\"cta-link\" href=\"/opportunities\">Browse live opportunities</a>
        </div>
        <div class=\"muted\" style=\"margin-top:8px;\">Free to start • No credit card</div>
    </section>
    """

    audience = """
    <section class=\"card\">
        <h2 class=\"section-heading\">Built for small businesses</h2>
        <div class=\"flex-grid\">
            <div>
                <div class=\"mini-head\">No portal hopping</div>
                <div class=\"mini-desc\">One place for city bids, documents, and deadlines.</div>
            </div>
            <div>
                <div class=\"mini-head\">Clear and timely</div>
                <div class=\"mini-desc\">Plain-language titles and due dates, emailed daily or weekly.</div>
            </div>
            <div>
                <div class=\"mini-head\">Right-fit opportunities</div>
                <div class=\"mini-desc\">Filter by agency and category to stay focused.</div>
            </div>
            <div>
                <div class=\"mini-head\">Growing with you</div>
                <div class=\"mini-desc\">Soon: file repository and a step-by-step bid tracker.</div>
            </div>
        </div>
    </section>
    """

    how = """
    <section class=\"card\">
        <h2 class=\"section-heading\">How it works</h2>
        <div class=\"flex-grid\">
            <div>
                <div class=\"mini-head\">1) Pick agencies</div>
                <div class=\"mini-desc\">Columbus, COTA, Gahanna, CRAA, and more.</div>
            </div>
            <div>
                <div class=\"mini-head\">2) Get email alerts</div>
                <div class=\"mini-desc\">We scan portals several times a day.</div>
            </div>
            <div>
                <div class=\"mini-head\">3) Track and file</div>
                <div class=\"mini-desc\">Save docs and follow a guided checklist (coming).</div>
            </div>
        </div>
    </section>
    """

    coverage = """
    <section class=\"card\">
        <h2 class=\"section-heading\">Coverage</h2>
        <p class=\"subtext\">Pilot focus on Central Ohio with expanding agencies.</p>
        <div class=\"flex-grid\">
            <div><span class=\"pill\">City of Columbus</span></div>
            <div><span class=\"pill\">COTA</span></div>
            <div><span class=\"pill\">SWACO</span></div>
            <div><span class=\"pill\">CRAA</span></div>
            <div><span class=\"pill\">Gahanna</span></div>
            <div><span class=\"pill\">Delaware County</span></div>
        </div>
        <div class=\"logo-row\" style=\"margin-top:10px;\">
            <img class=\"logo\" alt=\"Columbus\" src=\"/static/logos/columbus.svg\" onerror=\"this.style.display='none'\">
            <img class=\"logo\" alt=\"COTA\" src=\"/static/logos/cota.svg\" onerror=\"this.style.display='none'\">
            <img class=\"logo\" alt=\"SWACO\" src=\"/static/logos/swaco.svg\" onerror=\"this.style.display='none'\">
            <img class=\"logo\" alt=\"CRAA\" src=\"/static/logos/craa.svg\" onerror=\"this.style.display='none'\">
        </div>
    </section>
    """

    stats = """
    <section class=\"card\">
        <div class=\"stat-row\">
            <div class=\"stat\"><b>10+</b><span class=\"muted\">Agencies monitored</span></div>
            <div class=\"stat\"><b>Daily</b><span class=\"muted\">Email updates</span></div>
            <div class=\"stat\"><b>Minutes</b><span class=\"muted\">To get set up</span></div>
        </div>
    </section>
    """

    preview = """
    <section class=\"card\">
        <h2 class=\"section-heading\">What you’ll see</h2>
        <div class=\"mini-desc\">Clean opportunity cards with due dates, agency, and quick links.</div>
        <div class=\"table-wrap\" style=\"margin-top:10px;\">
            <table>
                <thead><tr><th>Title</th><th>Agency</th><th>Due</th><th>Category</th></tr></thead>
                <tbody>
                    <tr><td>On-call sidewalk repairs</td><td>City of Columbus</td><td>Mar 12</td><td>Construction</td></tr>
                    <tr><td>IT service desk support</td><td>COTA</td><td>Mar 18</td><td>IT Services</td></tr>
                    <tr><td>Creative design services</td><td>Gahanna</td><td>Mar 22</td><td>Marketing</td></tr>
                </tbody>
            </table>
        </div>
        <div style=\"margin-top:12px;\"><a class=\"cta-link\" href=\"/opportunities\">See current opportunities</a></div>
    </section>
    """

    email_sample = """
    <section class=\"card\">
        <h2 class=\"section-heading\">Email updates you’ll actually read</h2>
        <div class=\"mini-desc\">A quick morning summary with new and due-soon items.</div>
        <div style=\"font-size:13px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin-top:10px;\">
            <div><b>New today</b></div>
            <div>• City of Columbus — Snow removal equipment lease (Apr 2)</div>
            <div>• COTA — Network switches replacement (Mar 28)</div>
            <div style=\"margin-top:8px;\"><b>Due soon</b></div>
            <div>• Gahanna — Parks mowing services (Mar 14)</div>
        </div>
    </section>
    """

    closer = """
    <section class=\"card\" style=\"text-align:center;\">
        <h2 class=\"section-heading\">Ready to try it?</h2>
        <p class=\"subtext\">Create a free account and pick your agencies.</p>
        <a class=\"button-primary\" href=\"/signup\">Get Started</a>
    </section>
    """

    body_html = hero + audience + how + coverage + stats + preview + email_sample + closer
    return HTMLResponse(page_shell(body_html, title="EasyRFP • Win Local Bids Faster", user_email=user_email))


@router.get("/landing-test", response_class=HTMLResponse)
async def landing_test(request: Request):
    user_email = get_current_user_email(request)
    body_html = """
    <section class=\"card\" style=\"text-align:center;\">
        <h2 class=\"section-heading\">Simple landing test</h2>
        <p class=\"subtext\">This is a lightweight preview route kept for development.</p>
        <a class=\"button-primary\" href=\"/signup\">Try it free</a>
    </section>
    """
    return HTMLResponse(page_shell(body_html, title="EasyRFP • Preview", user_email=user_email))

