from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse, RedirectResponse

from app.api._layout import page_shell, _get_user_tier, _get_user_tier_info
from app.auth.session import get_current_user_email
from app.core.settings import settings
from app.core.db import AsyncSessionLocal
from sqlalchemy import text

router = APIRouter(tags=["billing"])


async def _sync_tier_from_stripe(user_email: str | None) -> None:
    """Best-effort: pull latest subscription for this email and update tier + IDs."""
    if not user_email:
        return
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not key or key.startswith("pk_"):
        return
    try:
        import stripe  # type: ignore
    except ModuleNotFoundError:
        return
    stripe.api_key = key
    try:
        # Find customer by email
        cust = None
        try:
            found = stripe.Customer.search(query=f"email:'{user_email}'", limit=1)
            cust = (found.get("data") or [None])[0]
        except Exception:
            found = stripe.Customer.list(email=user_email, limit=1)
            cust = (found.get("data") or [None])[0]
        if not cust:
            return
        customer_id = cust.get("id")

        subs = stripe.Subscription.list(customer=customer_id, status="all", limit=1)
        items = subs.get("data") or []
        if not items:
            return
        sub = items[0]
        price_id = ((sub.get("items") or {}).get("data") or [{}])[0].get("price", {}).get("id", "")
        price_to_tier = {
            (settings.STRIPE_PRICE_STARTER or "").lower(): "Starter",
            (settings.STRIPE_PRICE_PROFESSIONAL or "").lower(): "Professional",
            (settings.STRIPE_PRICE_ENTERPRISE or "").lower(): "Enterprise",
        }
        tier = price_to_tier.get(price_id.lower())
        if not tier:
            return
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    """
                    UPDATE users
                    SET tier = :tier,
                        stripe_customer_id = COALESCE(stripe_customer_id, :cid),
                        stripe_subscription_id = :sid
                    WHERE lower(email) = lower(:email)
                    """
                ),
                {"tier": tier, "email": user_email, "cid": customer_id, "sid": sub.get("id")},
            )
            await db.commit()
        try:
            print(f"[billing sync] refreshed tier for {user_email}: {tier} via subscription {sub.get('id')}")
        except Exception:
            pass
    except Exception:
        # Silent; this is best-effort
        return


async def _ensure_billing_owner(user_email: str | None):
    """
    Allow billing actions only for the team owner (or platform admin) when a team is present.
    """
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required")
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT id, team_id, is_admin FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
            {"email": user_email},
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Login required")
        user_id, team_id, is_admin = row
        if team_id:
            role_res = await db.execute(
                text("SELECT role FROM team_members WHERE team_id = :team AND user_id = :uid LIMIT 1"),
                {"team": team_id, "uid": user_id},
            )
            role = (role_res.scalar() or "").lower()
            if role != "owner" and not bool(is_admin):
                raise HTTPException(status_code=403, detail="Billing is restricted to the team owner.")


def _plan_card(name: str, price: str, highlights: list[str], cta_href: str, cta_label: str, current: bool) -> str:
    badge = '<span class="pill plan-pill">Current</span>' if current else ""
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
    tier_info = _get_user_tier_info(user_email)
    current_tier = tier_info.get("effective", "Free")

    # Restrict billing to team owner (or platform admin) when the user belongs to a team.
    if user_email:
        await _ensure_billing_owner(user_email)

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
"""
    status = request.query_params.get("status")
    banner = ""
    if status == "success":
        await _sync_tier_from_stripe(user_email)
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
async def billing_checkout(request: Request, plan: str = "starter", email: str | None = None, return_to: str | None = None):
    user_email = get_current_user_email(request) or (email or "").strip().lower()
    if not user_email:
        raise HTTPException(status_code=401, detail="Login required or email required")

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
    if return_to and return_to.startswith("/signup"):
        success_url = f"{base}{return_to}"
        cancel_url = f"{base}/signup?plan={plan}"

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
        # For Checkout Sessions we create (not payment links), pull plan from metadata or price.
        meta_plan = (data.get("metadata") or {}).get("plan", "")
        if meta_plan:
            tier = meta_plan.title()
        price_id_dbg = (data.get("line_items") or [{}])[0].get("price", "") if not tier else price_id_dbg

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
                    text(
                        """
                        INSERT OR IGNORE INTO users (email, password_hash, digest_frequency, agency_filter, is_active, created_at, tier)
                        VALUES (:email, '', 'daily', '[]', 1, CURRENT_TIMESTAMP, COALESCE(:tier, 'Free'))
                        """
                    ),
                    {"email": email, "tier": tier or "Free"},
                )
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
    await _ensure_billing_owner(user_email)
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
    info = _get_user_tier_info(email)
    return {"email": email, "tier": info.get("effective"), "label": info.get("label"), "source": info.get("source")}
