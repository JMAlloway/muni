# app/routers/marketing.py
import datetime as dt
import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api._layout import marketing_shell, page_shell
from app.auth.session import get_current_user_email
from app.services.opportunity_feed import fetch_landing_snapshot

router = APIRouter(tags=["marketing"])


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_email = get_current_user_email(request)
    try:
        stats, preview_rows = await fetch_landing_snapshot()
    except Exception:
        stats, preview_rows = {"total_open": 0, "closing_soon": 0, "added_recent": 0}, []

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

    hero_list = "".join(
        f"""
        <div class="list-item">
            <span class="bullet"></span>
            <span class="item-text">{html.escape(row.get("title") or "Opportunity")}</span>
            <span class="item-badge">Due {format_due(row.get("due_date"))}</span>
        </div>
        """
        for row in preview_rows[:3]
    ) or "<div class='list-item'><span class='item-text'>Fresh opportunities are populating...</span></div>"

    cta_url = "/dashboard" if user_email else "/signup"
    body_html = f"""
    <section class="hero">
      <div class="container">
        <div class="hero-content">
          <h1 class="hero-title">
            <span class="title-accent">Never miss a bid again.</span>
            <span class="title-main">Track every RFP across Central Ohio in one powerful dashboard.</span>
          </h1>
          <p class="hero-subtitle">
            Stop juggling 21 portals. Get instant alerts, smart summaries, and win rates that actually move the needle.
          </p>
          <div class="hero-buttons">
            <a href="{cta_url}" class="btn-cta">Start Tracking Free &rarr;</a>
            <a href="#features" class="btn-secondary">See How It Works</a>
          </div>
          <div class="trust-badges">
            <div class="trust-item"><span class="trust-label">Columbus</span></div>
            <div class="trust-item"><span class="trust-label">COTA</span></div>
            <div class="trust-item"><span class="trust-label">Franklin County</span></div>
            <div class="trust-item"><span class="trust-label">SWACO</span></div>
            <div class="trust-item"><span class="trust-label">Delaware Co.</span></div>
            <div class="trust-item"><span class="trust-label">CRAA</span></div>
          </div>
        </div>
      </div>
    </section>

    <section class="features-grid" id="features">
      <div class="container">
        <div class="feature-cards">
          <div class="feature-card">
            <div class="card-header">
              <h3 class="card-title">Real-time portal monitoring that actually works</h3>
              <span class="card-arrow">&rarr;</span>
            </div>
            <p class="card-description">Stop refreshing 21 different websites. We crawl, filter, and surface the opportunities that match your business&mdash;in real time.</p>
            <div class="card-preview">
              <div class="preview-stats">
                <div class="stat-item">
                  <div class="stat-label">Live Opportunities</div>
                  <div class="stat-value">{stats["total_open"]}</div>
                  <div class="stat-change">+{stats["added_recent"]} today</div>
                </div>
                <div class="stat-item">
                  <div class="stat-label">Closing Soon</div>
                  <div class="stat-value">{stats["closing_soon"]}</div>
                  <div class="stat-change">Next 7 days</div>
                </div>
              </div>
              <div class="preview-list">
                {hero_list}
              </div>
            </div>
          </div>

          <div class="feature-card card-blue">
            <div class="card-header">
              <h3 class="card-title">Team collaboration without the chaos</h3>
              <span class="card-arrow">&rarr;</span>
            </div>
            <p class="card-description">Assign owners, track progress, share files, and keep everyone in sync. All without leaving the platform.</p>
            <div class="card-preview">
              <div class="editor-illustration">
                <svg viewBox="0 0 100 100" class="check-icon">
                  <circle cx="50" cy="50" r="45" fill="rgba(78, 205, 196, 0.1)" stroke="rgba(78, 205, 196, 0.3)" stroke-width="2"/>
                  <path d="M30 50L45 65L70 35" stroke="#4ecdc4" stroke-width="5" fill="none" stroke-linecap="round"/>
                </svg>
                <div class="editor-box">
                  <div class="editor-title">High-Priority Bids</div>
                  <div class="editor-subtitle">Ready for your team</div>
                </div>
              </div>
              <div class="editor-actions">
                <button class="action-btn">Comments</button>
                <button class="action-btn">Files</button>
                <button class="action-btn">Track</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="trust-section">
      <div class="container">
        <h2 class="trust-title">Built for teams that win contracts, not waste time</h2>
        <div class="trust-stats">
          <div class="trust-stat"><span class="stat-icon">⚡</span><span>Launched 2024</span></div>
          <div class="trust-stat"><span class="stat-icon">⏱</span><span>24/7 monitoring</span></div>
          <div class="trust-stat"><span class="stat-icon">📡</span><span>21 portals tracked</span></div>
          <div class="trust-stat"><span class="stat-icon">🏅</span><span>150+ teams</span></div>
        </div>
      </div>
    </section>

    <section class="details-section" id="details">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">How it works</span>
          <h2 class="section-title">From alert to submission. No portal-hopping required.</h2>
          <p class="section-description">Everything you need to find, evaluate, and win government contracts&mdash;without the headache of tracking down opportunities across dozens of websites.</p>
        </div>

        <div class="details-grid">
          <div class="detail-card">
            <span class="detail-badge">Discovery</span>
            <h3 class="detail-title">We find them. You decide.</h3>
            <p class="detail-text">Automated crawling across 21 portals means you see every opportunity the moment it's posted&mdash;no manual checking required.</p>
            <ul class="detail-list">
              <li>Real-time alerts via email and SMS</li>
              <li>Smart filtering by category and budget</li>
              <li>Plain-English summaries with direct links</li>
            </ul>
          </div>

          <div class="detail-card">
            <span class="detail-badge accent">Prioritization</span>
            <h3 class="detail-title">Focus on what matters</h3>
            <p class="detail-text">Not every bid is worth pursuing. Our dashboard helps you quickly evaluate fit, timing, and competition.</p>
            <ul class="detail-list">
              <li>Due-date badges and urgency flags</li>
              <li>Saved searches and custom watchlists</li>
              <li>Historical data on similar contracts</li>
            </ul>
          </div>

          <div class="detail-card">
            <span class="detail-badge dark">Execution</span>
            <h3 class="detail-title">Ship proposals faster</h3>
            <p class="detail-text">Centralize files, assign tasks, and keep your whole team on the same page from first review to final submission.</p>
            <ul class="detail-list">
              <li>Status tracking with confidence scores</li>
              <li>File uploads and shared resources</li>
              <li>Team invites in under 30 seconds</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <section id="pricing" class="pricing-section">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">Pricing</span>
          <h2 class="section-title">Simple, transparent plans.</h2>
          <p class="section-description">Start free, upgrade when you need more seats and automation.</p>
        </div>
        <div class="pricing-grid">
          <div class="pricing-card">
            <h3 class="pricing-title">Starter</h3>
            <p class="pricing-price">Free</p>
            <p class="pricing-note">Great for trying alerts</p>
            <ul class="pricing-list">
              <li>Central Ohio coverage</li>
              <li>Email alerts &amp; summaries</li>
              <li>1 seat</li>
            </ul>
            <a href="{cta_url}" class="btn-primary">Get Started</a>
          </div>
          <div class="pricing-card featured">
            <h3 class="pricing-title">Team</h3>
            <p class="pricing-price">$79/mo</p>
            <p class="pricing-note">For capture teams</p>
            <ul class="pricing-list">
              <li>Unlimited seats</li>
              <li>Tasking &amp; file sharing</li>
              <li>SMS due-date alerts</li>
            </ul>
            <a href="{cta_url}" class="btn-cta">Try Team</a>
          </div>
          <div class="pricing-card">
            <h3 class="pricing-title">Enterprise</h3>
            <p class="pricing-price">Let&rsquo;s talk</p>
            <p class="pricing-note">Multi-region coverage</p>
            <ul class="pricing-list">
              <li>Custom portals &amp; SLAs</li>
              <li>Dedicated CSM</li>
              <li>SAML &amp; audit trails</li>
            </ul>
            <a href="/contact" class="btn-secondary">Contact Sales</a>
          </div>
        </div>
      </div>
    </section>

    <section id="coverage" class="coverage-section">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">Coverage Area</span>
          <h2 class="section-title">Central Ohio today. Your region tomorrow.</h2>
          <p class="section-description">We're actively expanding. Tell us which portals you need and we'll add them to the queue.</p>
        </div>
        <div class="coverage-grid">
          <span class="coverage-badge">City of Columbus</span>
          <span class="coverage-badge">COTA</span>
          <span class="coverage-badge">SWACO</span>
          <span class="coverage-badge">CRAA</span>
          <span class="coverage-badge">Gahanna</span>
          <span class="coverage-badge">Delaware County</span>
          <span class="coverage-badge">Franklin County</span>
          <span class="coverage-badge">Westerville</span>
          <span class="coverage-badge">Dublin</span>
          <span class="coverage-badge">Upper Arlington</span>
          <span class="coverage-badge">Worthington</span>
          <span class="coverage-badge">Grove City</span>
          <span class="coverage-badge">Hilliard</span>
          <span class="coverage-badge">Reynoldsburg</span>
          <span class="coverage-badge">Pickerington</span>
        </div>
      </div>
    </section>

    <section id="signup" class="cta-section">
      <div class="container">
        <div class="cta-content">
          <span class="section-badge">Ready to win?</span>
          <h2 class="cta-title">Start tracking opportunities in the next 90 seconds.</h2>
          <p class="cta-description">No credit card. No contracts. Just a cleaner way to find and win government bids.</p>
          <div class="cta-buttons">
            <a href="{cta_url}" class="btn-cta">Create Free Account &rarr;</a>
            <a href="/opportunities" class="btn-secondary">View Live Opportunities</a>
          </div>
        </div>
      </div>
    </section>

    <section id="contact" class="contact-section">
      <div class="container contact-grid">
        <div class="contact-copy">
          <h3>Need something custom?</h3>
          <p>Tell us which portals you need added, or ask for a quick demo.</p>
        </div>
        <div class="contact-actions">
          <a href="mailto:hello@easyrfp.com" class="btn-secondary">Email us</a>
          <a href="/contact" class="btn-primary">Talk to Sales</a>
        </div>
      </div>
    </section>
    """

    return HTMLResponse(
        marketing_shell(body_html, title="EasyRFP - Win Local Bids Faster", user_email=user_email)
    )


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
    return HTMLResponse(page_shell(body_html, title="EasyRFP - Preview", user_email=user_email))
