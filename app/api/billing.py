from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse, RedirectResponse

from app.api._layout import page_shell, _get_user_tier
from app.auth.session import get_current_user_email
from app.core.settings import settings
from app.core.db import AsyncSessionLocal
from sqlalchemy import text

router = APIRouter(tags=["billing"])


def _plan_card(name: str, price: str, highlights: list[str], cta_href: str, cta_label: str, current: bool) -> str:
    badge = '<span class="pill">Current</span>' if current else ""
    btn_class = "btn-secondary" if current else "btn"
    btn_attrs = 'aria-disabled="true" tabindex="-1"' if current else ""
    items = "".join([f"<li>{h}</li>" for h in highlights])
    return f"""
    <article class="plan-card {'plan-current' if current else ''}">
      <div class="plan-head">
        <div>
          <div class="plan-name">{name} {badge}</div>
          <div class="plan-price">{price}</div>
        </div>
        <a class="{btn_class}" href="{cta_href}" {btn_attrs}>{cta_label}</a>
      </div>
      <ul class="plan-list">{items}</ul>
    </article>
    """


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    user_email = get_current_user_email(request)
    current_tier = _get_user_tier(user_email).title()

    payment_links = {
        "Starter": "https://buy.stripe.com/test_6oUfZj4DeaNkdzO3NXcV201",
        "Professional": "https://buy.stripe.com/test_dRm00ld9K08G7bqbgpcV202",
        "Enterprise": "https://buy.stripe.com/test_aFa9AVglW2gOanCcktcV200",
    }

    plans = [
        {
            "name": "Free",
            "price": "$0",
            "highlights": [
                "View opportunities (24h delay)",
                "Track up to 3 bids",
                "Weekly digest emails",
            ],
        },
        {
            "name": "Starter",
            "price": "$29/mo",
            "highlights": [
                "Real-time opportunity updates",
                "Track unlimited bids",
                "Daily digests",
                "Email alerts for keywords",
                "File uploads (5GB)",
            ],
        },
        {
            "name": "Professional",
            "price": "$99/mo",
            "highlights": [
                "Everything in Starter",
                "AI-powered bid matching",
                "Proposal templates",
                "Team collaboration (3 users)",
                "Priority support",
                "Vendor registration guides",
            ],
        },
        {
            "name": "Enterprise",
            "price": "$299/mo",
            "highlights": [
                "Everything in Pro",
                "Unlimited team members",
                "Custom agency coverage",
                "API access",
                "Win/loss analytics",
            ],
        },
    ]

    cards = []
    for plan in plans:
        name = plan["name"]
        current = current_tier.lower() == name.lower()
        href = payment_links.get(name, "#")
        label = "Current plan" if current else "Upgrade"
        cards.append(
            _plan_card(
                name=name,
                price=plan["price"],
                highlights=plan["highlights"],
                cta_href=href,
                cta_label=label,
                current=current,
            )
        )

    cards_html = "".join(cards)
    script_html = """
<script>
(function(){
  const links = document.querySelectorAll('.plan-card .btn');
  links.forEach(function(btn){
    if (btn.getAttribute('aria-disabled') === 'true') return;
    btn.addEventListener('click', function(ev){
      ev.preventDefault();
      const url = btn.getAttribute('href');
      if (!url) return;
      window.open(url, '_blank', 'noopener');
    });
  });
  async function syncTier(){
    try {
      const res = await fetch('/billing/debug-tier', { credentials:'include' });
      if (!res.ok) return;
      const data = await res.json();
      const tier = (data.tier || '').toString();
      if (!tier) return;
      const pill = document.querySelector('.top-tier strong');
      if (pill) pill.textContent = tier;
      document.querySelectorAll('.plan-card').forEach(function(card){
        const nameEl = card.querySelector('.plan-name');
        const btn = card.querySelector('.btn, .btn-secondary');
        if (!nameEl || !btn) return;
        const isCurrent = (nameEl.textContent||'').toLowerCase().includes(tier.toLowerCase());
        if (isCurrent){
          btn.className = 'btn-secondary';
          btn.setAttribute('aria-disabled','true');
          btn.setAttribute('tabindex','-1');
          btn.textContent = 'Current plan';
        } else {
          btn.className = 'btn';
          btn.removeAttribute('aria-disabled');
          btn.removeAttribute('tabindex');
          btn.textContent = 'Upgrade';
        }
      });
    } catch(e){}
  }
  syncTier();
  const manageBtn = document.getElementById('manage-sub');
  if (manageBtn) {
    manageBtn.addEventListener('click', async function(){
      try {
        const res = await fetch('/billing/portal', { credentials:'include' });
        if (!res.ok) throw new Error('Portal unavailable');
        const data = await res.json();
        if (data && data.url) {
          window.open(data.url, '_blank', 'noopener');
        }
      } catch(_) { alert('Could not open subscription management.'); }
    });
  }
})();
</script>
"""
    style_html = """
<style>
.plan-grid {
  display:grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap:12px;
}
.plan-card {
  border:1px solid #e5e7eb;
  border-radius:16px;
  padding:14px;
  background:#fff;
  box-shadow:0 6px 14px rgba(15,23,42,0.08);
  display:grid;
  gap:10px;
}
.plan-current { border-color: rgba(49,179,124,0.4); box-shadow:0 0 0 2px rgba(49,179,124,0.15); }
.plan-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.plan-name { font-weight:700; font-size:16px; }
.plan-price { color:#475569; font-weight:600; }
.plan-list { list-style:none; padding:0; margin:0; display:grid; gap:6px; color:#334155; font-size:13px; }
.plan-list li::before { content:'• '; color:#31b37c; }
.btn { background:#2563eb; color:#fff; padding:8px 10px; border-radius:10px; text-decoration:none; font-weight:600; }
.btn-secondary { background:#f1f5f9; color:#0f172a; padding:8px 10px; border-radius:10px; text-decoration:none; font-weight:600; pointer-events:auto; opacity:1; }
.btn-secondary[aria-disabled="true"] { pointer-events:none; opacity:0.8; }
.pill { display:inline-block; padding:2px 8px; border-radius:999px; background:rgba(49,179,124,0.14); color:#126a45; font-size:11px; margin-left:6px; }
</style>
"""
    status = request.query_params.get("status")
    banner = ""
    if status == "success":
        banner = '<div class="alert success">Payment received. Your plan will update shortly.</div>'
    elif status == "cancel":
        banner = '<div class="alert muted">Checkout canceled.</div>'

    body = f"""
<section class="card">
  <h2 class="section-heading">Billing & Plans</h2>
  <p class="subtext">Choose the plan that fits your team. Upgrade links open Stripe payment pages.</p>
  {banner}
  <div style="margin-bottom:10px;">
    <button class="btn-secondary" type="button" id="manage-sub">Manage / cancel subscription</button>
  </div>
  <div class="plan-grid">
    {cards_html}
  </div>
</section>
{script_html}
{style_html}
    """

    return HTMLResponse(page_shell(body, title="Billing", user_email=user_email))


@router.get("/billing/checkout")
async def billing_checkout(request: Request, plan: str = "starter"):
    user_email = get_current_user_email(request)
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")

    # Configure Stripe
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        import stripe  # type: ignore
    except ModuleNotFoundError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")
    stripe.api_key = key

    plan_map = {
        "starter": settings.STRIPE_PRICE_STARTER,
        "professional": settings.STRIPE_PRICE_PROFESSIONAL,
        "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
    }
    price_id = plan_map.get(plan.lower())
    if not price_id:
        raise HTTPException(status_code=400, detail="Unknown plan")

    base = str(request.base_url).rstrip("/")
    success_url = f"{base}/billing?status=success"
    cancel_url = f"{base}/billing?status=cancel"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"email": user_email, "plan": plan.lower()},
        )
    except Exception as exc:  # pragma: no cover
        # Avoid leaking keys; return a generic error
        raise HTTPException(status_code=502, detail="Stripe error: check API key and price IDs") from exc

    # If this was triggered from a browser (e.g., signup), redirect straight to Stripe.
    # Default to redirect on GET to keep the flow intuitive; API clients can POST and read JSON.
    accept = request.headers.get("accept", "")
    if request.method == "GET" or "text/html" in accept:
        return RedirectResponse(session.url, status_code=303)
    return {"url": session.url}


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    # Validate config
    secret = (settings.STRIPE_WEBHOOK_SECRET or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")
    try:
        import stripe  # type: ignore
    except ModuleNotFoundError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=secret)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    data = event.get("data", {}).get("object", {})
    event_type = event.get("type")

    # Map payment link URLs and price IDs to tiers (avoids Stripe API calls)
    payment_link_to_tier = {
        "plink_1swsbrpdgbpr3k66cvbrok20": "Starter",
        "plink_1swscopdgbpr3k662btzu4vu": "Professional",
        "plink_1swsanpdgbpr3k66wmh1u0oa": "Enterprise",
    }
    price_to_tier = {
        (settings.STRIPE_PRICE_STARTER or "").lower(): "Starter",
        (settings.STRIPE_PRICE_PROFESSIONAL or "").lower(): "Professional",
        (settings.STRIPE_PRICE_ENTERPRISE or "").lower(): "Enterprise",
    }

    # Handle checkout.session.completed (payment links create Checkout Sessions)
    tier = None
    email = None
    price_id_dbg = ""
    customer_id = data.get("customer") or None
    subscription_id = data.get("subscription") or None

    if event_type == "checkout.session.completed":
        email = (
            data.get("customer_details", {}) or {}
        ).get("email") or data.get("customer_email")
        link = (data.get("payment_link") or "").lower()
        tier = payment_link_to_tier.get(link)
        customer_id = data.get("customer") or customer_id
        subscription_id = data.get("subscription") or subscription_id

    if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
        email = data.get("customer_email") or email
        customer_id = data.get("customer") or customer_id
        subscription_id = data.get("subscription") or subscription_id
        lines = (data.get("lines") or {}).get("data") or []
        if lines:
            price_id = (lines[0].get("price") or {}).get("id", "")
            price_id_dbg = price_id
            tier = price_to_tier.get(price_id.lower())

    if email and (tier or customer_id or subscription_id):
        updates = {"email": email}
        set_parts = []
        if tier:
            updates["tier"] = tier
            set_parts.append("tier = :tier")
        if customer_id:
            updates["stripe_customer_id"] = customer_id
            set_parts.append("stripe_customer_id = :stripe_customer_id")
        if subscription_id:
            updates["stripe_subscription_id"] = subscription_id
            set_parts.append("stripe_subscription_id = :stripe_subscription_id")
        if set_parts:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text(f"UPDATE users SET {', '.join(set_parts)} WHERE lower(email) = lower(:email)"),
                    updates,
                )
                await db.commit()
        try:
            print(
                f"[stripe webhook] type={event_type} email={email} tier={tier} customer={customer_id} subscription={subscription_id}"
            )
        except Exception:
            pass
    else:
        try:
            print(f"[stripe webhook] type={event_type} email={email} payment_link={data.get('payment_link')} price_id={price_id_dbg} tier_resolved={tier}")
        except Exception:
            pass

    return {"received": True}


@router.get("/billing/portal", response_class=JSONResponse, include_in_schema=False)
async def billing_portal(request: Request):
    user_email = get_current_user_email(request)
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")
    if not key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    if key.startswith("pk_"):
        raise HTTPException(status_code=503, detail="Stripe secret key invalid; use your secret (sk_) key")
    try:
        import stripe  # type: ignore
    except ModuleNotFoundError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")
    stripe.api_key = key
    try:
        stored_customer_id = None
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                text(
                    "SELECT stripe_customer_id FROM users WHERE lower(email) = lower(:email) LIMIT 1"
                ),
                {"email": user_email},
            )
            row = res.fetchone()
            stored_customer_id = row[0] if row else None

        customer_id = stored_customer_id
        try:
            print(f"[stripe portal] stored_customer_id={stored_customer_id} for {user_email}")
        except Exception:
            pass
        items = []
        try:
            if not customer_id:
                customers = stripe.Customer.search(query=f"email:'{user_email}'")
                items = customers.get("data") or []
        except Exception:
            if not customer_id:
                customers = stripe.Customer.list(email=user_email, limit=1)
                items = customers.get("data") or []
        if not customer_id and items:
            customer_id = items[0]["id"]
        if not customer_id:
            created = stripe.Customer.create(email=user_email, name=user_email)
            customer_id = created["id"]
            try:
                print(f"[stripe portal] created new Stripe customer {customer_id} for {user_email}")
            except Exception:
                pass
        if customer_id and customer_id != stored_customer_id:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO users (email, password_hash, digest_frequency, created_at, tier)
                        VALUES (:email, '', 'weekly', datetime('now'), 'free')
                        """
                    ),
                    {"email": user_email},
                )
                await db.execute(
                    text(
                        "UPDATE users SET stripe_customer_id = :cid WHERE lower(email) = lower(:email)"
                    ),
                    {"cid": customer_id, "email": user_email},
                )
                await db.commit()
            try:
                print(f"[stripe portal] saved customer_id for {user_email}: {customer_id}")
            except Exception:
                pass
            # Verify persisted value for debugging
            try:
                async with AsyncSessionLocal() as db:
                    check = await db.execute(
                        text(
                            "SELECT stripe_customer_id FROM users WHERE lower(email) = lower(:email) LIMIT 1"
                        ),
                        {"email": user_email},
                    )
                    row = check.fetchone()
                    persisted = row[0] if row else None
                    print(f"[stripe portal] persisted stripe_customer_id={persisted} for {user_email}")
            except Exception:
                pass
        else:
            try:
                print(f"[stripe portal] using existing customer_id for {user_email}: {customer_id}")
            except Exception:
                pass
        base = str(request.base_url).rstrip("/")
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{base}/billing",
        )
        return {"url": session.url}
    except stripe.error.AuthenticationError:
        raise HTTPException(status_code=503, detail="Stripe authentication failed; check STRIPE_SECRET_KEY")
    except stripe.error.InvalidRequestError as exc:
        detail = exc.user_message or exc.code or "Stripe invalid request"
        raise HTTPException(status_code=400, detail=f"Stripe portal error: {detail}")
    except stripe.error.StripeError as exc:
        detail = exc.user_message or exc.code or "Stripe error"
        raise HTTPException(status_code=502, detail=detail)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        try:
            print(f"[stripe portal] unexpected error: {exc}")
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Could not create portal session") from exc


@router.get("/billing/debug-tier", response_class=JSONResponse, include_in_schema=False)
async def billing_debug_tier(request: Request):
    email = get_current_user_email(request)
    tier = _get_user_tier(email)
    return {"email": email, "tier": tier}
