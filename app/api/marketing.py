# app/routers/marketing.py

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
        stats, _ = await fetch_landing_snapshot()
    except Exception:
        stats, _ = {"total_open": 0, "closing_soon": 0, "added_recent": 0}, []

    cta_url = "/signup"
    active_opps = stats.get("total_open", 0)
    closing_soon = stats.get("closing_soon", 0)
    recently_added = stats.get("added_recent", 0)

    body_html = f"""
    <section class="hero">
      <div class="container">
        <div class="hero-content">
          <div class="hero-badge">Trusted by 150+ Central Ohio contractors</div>
          <h1 class="hero-title">
            <span class="title-accent">Win more bids.</span>
            <span class="title-main">Spend less time searching.</span>
          </h1>
          <p class="hero-subtitle">
            EasyRFP monitors 21 government portals across Central Ohio, delivers plain-English summaries, and helps your team respond faster with built-in collaboration tools.
          </p>
          <div class="hero-buttons">
            <a href="{cta_url}" class="btn-cta">Start Free Trial</a>
            <a href="/opportunities" class="btn-secondary">View Live Opportunities</a>
          </div>
          <div class="hero-metrics">
            <div class="metric">
              <span class="metric-value">{active_opps}</span>
              <span class="metric-label">Active Opportunities</span>
            </div>
            <div class="metric">
              <span class="metric-value">21</span>
              <span class="metric-label">Portals Monitored</span>
            </div>
            <div class="metric">
              <span class="metric-value">24/7</span>
              <span class="metric-label">Real-time Alerts</span>
            </div>
            <div class="metric">
              <span class="metric-value">5min</span>
              <span class="metric-label">Avg. Alert Speed</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="trust-section">
      <div class="container">
        <p class="trust-label">Monitoring opportunities from Central Ohio agencies</p>
        <div class="trust-logos">
          <span class="trust-logo">City of Columbus</span>
          <span class="trust-logo">COTA</span>
          <span class="trust-logo">Franklin County</span>
          <span class="trust-logo">SWACO</span>
          <span class="trust-logo">CRAA</span>
          <span class="trust-logo">Delaware County</span>
        </div>
      </div>
    </section>

    <section class="stats-section">
      <div class="container">
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-number">{active_opps}</div>
            <div class="stat-text">Active opportunities right now</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">{closing_soon}</div>
            <div class="stat-text">Closing within 7 days</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">21</div>
            <div class="stat-text">Government portals tracked</div>
          </div>
          <div class="stat-card">
            <div class="stat-number">+{recently_added}</div>
            <div class="stat-text">Newly added today</div>
          </div>
        </div>
      </div>
    </section>

    <section class="features-section" id="features">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">Features</span>
          <h2 class="section-title">Everything you need to win contracts</h2>
          <p class="section-description">Stop juggling spreadsheets and browser tabs. EasyRFP gives your team a single source of truth for every government opportunity.</p>
        </div>
        <div class="features-grid">
          <div class="feature-card">
            <div class="feature-number">1</div>
            <h3>Real-time Portal Monitoring</h3>
            <p>We crawl 21 Central Ohio portals every hour, so you see new opportunities within minutes of posting.</p>
            <ul>
              <li>Instant email and SMS alerts</li>
              <li>Smart filtering by category</li>
              <li>Plain-English bid summaries</li>
            </ul>
          </div>

          <div class="feature-card">
            <div class="feature-number blue">2</div>
            <h3>Deadline Calendar</h3>
            <p>Visualize all your tracked bids on a unified calendar with color-coded urgency levels.</p>
            <ul>
              <li>Monthly, weekly, and list views</li>
              <li>Deadline reminders via email</li>
              <li>Team-wide calendar sync</li>
            </ul>
          </div>

          <div class="feature-card">
            <div class="feature-number orange">3</div>
            <h3>Document Management</h3>
            <p>Keep all your proposals, templates, and contracts organized in one searchable place.</p>
            <ul>
              <li>Folder organization by bid</li>
              <li>Version history tracking</li>
              <li>Template library</li>
            </ul>
          </div>

          <div class="feature-card">
            <div class="feature-number purple">4</div>
            <h3>Team Collaboration</h3>
            <p>Assign bid owners, track progress, share notes, and keep everyone aligned.</p>
            <ul>
              <li>Role-based permissions</li>
              <li>Activity feed and comments</li>
              <li>Progress tracking per bid</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <section class="how-it-works" id="how-it-works">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">How It Works</span>
          <h2 class="section-title">From alert to submission in three steps</h2>
        </div>
        <div class="steps-grid">
          <div class="step">
            <div class="step-number">1</div>
            <h3>We Find Opportunities</h3>
            <p>Our system crawls 21 government portals every hour. You get instant alerts when relevant bids are posted.</p>
          </div>
          <div class="step">
            <div class="step-number">2</div>
            <h3>You Evaluate & Track</h3>
            <p>Review summaries, check deadlines, and add promising bids to your tracking list with one click.</p>
          </div>
          <div class="step">
            <div class="step-number">3</div>
            <h3>Your Team Executes</h3>
            <p>Assign owners, upload documents, track progress, and submit winning proposals on time.</p>
          </div>
        </div>
      </div>
    </section>

    <section class="pricing-section" id="pricing">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">Pricing</span>
          <h2 class="section-title">Plans that grow with your business</h2>
          <p class="section-description">Start free, upgrade when you're ready. No credit card required.</p>
        </div>
        <div class="pricing-grid">
          <div class="pricing-card">
            <h3 class="pricing-name">Starter</h3>
            <p class="pricing-desc">For individuals exploring government contracts</p>
            <div class="pricing-price">
              <span class="price">$0</span>
              <span class="period">/month</span>
            </div>
            <ul class="pricing-features">
              <li>5 tracked opportunities</li>
              <li>Daily email digest</li>
              <li>Basic search & filters</li>
              <li>7-day bid history</li>
            </ul>
            <a href="{cta_url}" class="pricing-btn secondary">Get Started Free</a>
          </div>

          <div class="pricing-card featured">
            <div class="popular-badge">Most Popular</div>
            <h3 class="pricing-name">Professional</h3>
            <p class="pricing-desc">For growing contractors and small teams</p>
            <div class="pricing-price">
              <span class="price">$99</span>
              <span class="period">/month</span>
            </div>
            <ul class="pricing-features">
              <li>Unlimited tracked opportunities</li>
              <li>Real-time SMS & email alerts</li>
              <li>Advanced filters & saved searches</li>
              <li>Full bid history</li>
              <li>Document storage (5GB)</li>
              <li>Calendar integration</li>
            </ul>
            <a href="{cta_url}" class="pricing-btn">Start 14-Day Trial</a>
          </div>

          <div class="pricing-card">
            <h3 class="pricing-name">Team</h3>
            <p class="pricing-desc">For established firms with capture teams</p>
            <div class="pricing-price">
              <span class="price">$239</span>
              <span class="period">/month</span>
            </div>
            <ul class="pricing-features">
              <li>Everything in Professional</li>
              <li>Up to 10 team members</li>
              <li>Role-based permissions</li>
              <li>Document storage (50GB)</li>
              <li>Team activity dashboard</li>
              <li>Dedicated account manager</li>
            </ul>
            <a href="/contact" class="pricing-btn secondary">Contact Sales</a>
          </div>
        </div>
      </div>
    </section>

    <section class="testimonials-section">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">Testimonials</span>
          <h2 class="section-title">Trusted by contractors across Central Ohio</h2>
        </div>
        <div class="testimonials-grid">
          <div class="testimonial">
            <p class="testimonial-text">"EasyRFP cut our opportunity research time by 80%. We used to spend hours every week checking different portals. Now everything comes to us."</p>
            <div class="testimonial-author">
              <div class="author-avatar">MK</div>
              <div>
                <div class="author-name">Michael Kennedy</div>
                <div class="author-title">CEO, Kennedy Construction</div>
              </div>
            </div>
          </div>
          <div class="testimonial">
            <p class="testimonial-text">"The team collaboration features are game-changing. Our capture manager, estimators, and proposal writers are finally on the same page."</p>
            <div class="testimonial-author">
              <div class="author-avatar">SR</div>
              <div>
                <div class="author-name">Sarah Rodriguez</div>
                <div class="author-title">VP Operations, TechServe Ohio</div>
              </div>
            </div>
          </div>
          <div class="testimonial">
            <p class="testimonial-text">"We never miss a deadline anymore. The calendar view and reminder system have completely changed how we manage our pipeline."</p>
            <div class="testimonial-author">
              <div class="author-avatar">JT</div>
              <div>
                <div class="author-name">James Thompson</div>
                <div class="author-title">Owner, Thompson & Associates</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="coverage" class="coverage-section">
      <div class="container">
        <div class="section-header">
          <span class="section-badge">Coverage Area</span>
          <h2 class="section-title">Central Ohio today. Expanding soon.</h2>
          <p class="section-description">We're actively adding new portals. Request coverage for your region.</p>
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
          <h2 class="cta-title">Ready to win more government contracts?</h2>
          <p class="cta-description">Join 150+ contractors who use EasyRFP to find opportunities faster and submit winning proposals on time.</p>
          <div class="cta-buttons">
            <a href="{cta_url}" class="btn-cta">Start Your Free Trial</a>
            <a href="/opportunities" class="btn-secondary">View Live Opportunities</a>
          </div>
          <p class="cta-note">No credit card required. 14-day free trial on Professional plan.</p>
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


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    """Privacy policy page"""
    user_email = get_current_user_email(request)
    body_html = """
    <div style="max-width: 800px; margin: 0 auto; padding: 40px 20px;">
        <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 16px; color: #1f2937;">Privacy Policy</h1>
        <p style="color: #6b7280; margin-bottom: 32px;">Last updated: December 19, 2024</p>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Introduction</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                EasyRFP ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains
                how we collect, use, disclose, and safeguard your information when you use our service.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Information We Collect</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We collect information that you provide directly to us, including:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li>Account information (name, email address, password)</li>
                <li>Company profile information</li>
                <li>Billing information (processed securely via Stripe)</li>
                <li>Documents and content you upload to our platform</li>
                <li>Communications with our support team</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">How We Use Your Information</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We use the information we collect to:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li>Provide, maintain, and improve our services</li>
                <li>Send you RFP/RFQ opportunity alerts and notifications</li>
                <li>Process your payments and manage your subscription</li>
                <li>Communicate with you about service updates and support</li>
                <li>Analyze usage patterns to enhance user experience</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Cookies and Tracking</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We use cookies and similar tracking technologies to provide functionality and enhance your experience.
                For detailed information about our cookie usage, please see our <a href="/cookies" style="color: #126a45; text-decoration: underline;">Cookie Policy</a>.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Data Security</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We implement appropriate technical and organizational measures to protect your personal information.
                However, no method of transmission over the internet is 100% secure, and we cannot guarantee absolute security.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Third-Party Services</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We use the following third-party services:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li><strong>Stripe</strong> - Payment processing (only if you consent to payment processing cookies)</li>
                <li><strong>Twilio</strong> - SMS notifications (optional)</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Your Rights</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                You have the right to:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li>Access, update, or delete your personal information</li>
                <li>Opt out of marketing communications</li>
                <li>Request a copy of your data</li>
                <li>Withdraw consent for optional data processing</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Contact Us</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                If you have questions about this Privacy Policy, please contact us at:
                <a href="/support" style="color: #126a45; text-decoration: underline;">support</a>
            </p>
        </section>

        <div style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
            <a href="/" style="color: #126a45; text-decoration: underline;">← Back to home</a>
        </div>
    </div>
    """
    return HTMLResponse(page_shell(body_html, title="Privacy Policy - EasyRFP", user_email=user_email))


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    """Terms of service page"""
    user_email = get_current_user_email(request)
    body_html = """
    <div style="max-width: 800px; margin: 0 auto; padding: 40px 20px;">
        <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 16px; color: #1f2937;">Terms of Service</h1>
        <p style="color: #6b7280; margin-bottom: 32px;">Last updated: December 19, 2024</p>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Acceptance of Terms</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                By accessing and using EasyRFP, you accept and agree to be bound by these Terms of Service.
                If you do not agree to these terms, please do not use our service.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Description of Service</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                EasyRFP provides a platform for monitoring government RFP/RFQ opportunities, managing bid tracking,
                document storage, and team collaboration for contractors and businesses.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">User Accounts</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                You are responsible for:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li>Maintaining the confidentiality of your account credentials</li>
                <li>All activities that occur under your account</li>
                <li>Notifying us immediately of any unauthorized use</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Acceptable Use</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                You agree not to:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li>Use the service for any illegal purpose</li>
                <li>Attempt to gain unauthorized access to our systems</li>
                <li>Interfere with or disrupt the service</li>
                <li>Share your account with others</li>
                <li>Scrape or automatically harvest data from the platform</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Subscription and Billing</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                Paid subscriptions are billed monthly or annually as selected. You may cancel at any time,
                and cancellation will take effect at the end of your current billing period.
                No refunds are provided for partial billing periods.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Data Accuracy</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                While we strive to provide accurate and up-to-date information about government opportunities,
                we do not guarantee the accuracy, completeness, or timeliness of the data. Users should verify
                all information directly with the issuing agency before submitting proposals.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Limitation of Liability</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                EasyRFP shall not be liable for any indirect, incidental, special, consequential, or punitive damages
                resulting from your use of or inability to use the service, including but not limited to missed bid
                opportunities or deadlines.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Termination</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We reserve the right to suspend or terminate your account at any time for violation of these terms
                or for any other reason at our sole discretion.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Changes to Terms</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We may update these terms from time to time. Continued use of the service after changes
                constitutes acceptance of the updated terms.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Contact</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                Questions about these terms? Contact us at <a href="/support" style="color: #126a45; text-decoration: underline;">support</a>
            </p>
        </section>

        <div style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
            <a href="/" style="color: #126a45; text-decoration: underline;">← Back to home</a>
        </div>
    </div>
    """
    return HTMLResponse(page_shell(body_html, title="Terms of Service - EasyRFP", user_email=user_email))


@router.get("/cookies", response_class=HTMLResponse)
async def cookie_policy(request: Request):
    """Cookie policy page"""
    user_email = get_current_user_email(request)
    body_html = """
    <div style="max-width: 800px; margin: 0 auto; padding: 40px 20px;">
        <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 16px; color: #1f2937;">Cookie Policy</h1>
        <p style="color: #6b7280; margin-bottom: 32px;">Last updated: December 19, 2024</p>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">What Are Cookies?</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                Cookies are small text files stored on your device when you visit a website. They help websites
                remember your preferences and provide functionality.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">How We Use Cookies</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                EasyRFP uses cookies for the following purposes:
            </p>
        </section>

        <section style="margin-bottom: 32px; padding: 20px; background: #f9fafb; border-radius: 8px;">
            <h3 style="font-size: 18px; font-weight: 600; margin-bottom: 12px; color: #1f2937;">Essential Cookies (Always Active)</h3>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 12px;">
                These cookies are necessary for the website to function and cannot be disabled.
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px;">
                <li><strong>muni_session</strong> - Keeps you logged in (30 days)</li>
                <li><strong>csrftoken</strong> - Protects against security attacks (session)</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px; padding: 20px; background: #f9fafb; border-radius: 8px;">
            <h3 style="font-size: 18px; font-weight: 600; margin-bottom: 12px; color: #1f2937;">Analytics Cookies (Optional)</h3>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 12px;">
                Currently not in use. If we add analytics in the future, you'll be able to opt in/out.
            </p>
        </section>

        <section style="margin-bottom: 32px; padding: 20px; background: #f9fafb; border-radius: 8px;">
            <h3 style="font-size: 18px; font-weight: 600; margin-bottom: 12px; color: #1f2937;">Payment Processing Cookies (Optional)</h3>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 12px;">
                When you upgrade your account, Stripe (our payment processor) may set cookies to:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 12px;">
                <li>Process payments securely</li>
                <li>Prevent fraud</li>
                <li>Remember your payment details (if you choose)</li>
            </ul>
            <p style="line-height: 1.6; color: #6b7280; font-size: 14px;">
                These cookies are only set if you consent to payment processing and visit billing pages.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Managing Your Cookie Preferences</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                You can manage your cookie preferences at any time by:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li>Clicking the cookie preferences link in the banner (if shown)</li>
                <li>Visiting your <a href="/account#cookies" style="color: #126a45; text-decoration: underline;">account settings</a></li>
                <li>Adjusting your browser settings to block cookies (may affect site functionality)</li>
            </ul>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Third-Party Cookies</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We only use third-party cookies from:
            </p>
            <ul style="line-height: 1.8; color: #374151; margin-left: 24px; margin-bottom: 16px;">
                <li><strong>Stripe</strong> - Payment processing (requires consent)</li>
            </ul>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We do not use advertising cookies or tracking for marketing purposes.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Your Consent</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                By clicking "Accept All" in the cookie banner, you consent to our use of optional cookies.
                You can withdraw consent at any time through your account settings.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Updates to This Policy</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                We may update this Cookie Policy from time to time. The "Last updated" date at the top
                indicates when changes were last made.
            </p>
        </section>

        <section style="margin-bottom: 32px;">
            <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 16px; color: #1f2937;">Questions?</h2>
            <p style="line-height: 1.6; color: #374151; margin-bottom: 16px;">
                If you have questions about our use of cookies, contact us at
                <a href="/support" style="color: #126a45; text-decoration: underline;">support</a> or view our
                <a href="/privacy" style="color: #126a45; text-decoration: underline;">Privacy Policy</a>.
            </p>
        </section>

        <div style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
            <a href="/" style="color: #126a45; text-decoration: underline;">← Back to home</a>
        </div>
    </div>
    """
    return HTMLResponse(page_shell(body_html, title="Cookie Policy - EasyRFP", user_email=user_email))
