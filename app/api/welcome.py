import datetime as dt
import html
from typing import List, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api._layout import page_shell
from app.auth.auth_utils import require_login
from app.onboarding.interests import (
    DEFAULT_INTEREST_KEY,
    get_interest_profile,
    interest_label,
)
from app.services import (
    fetch_interest_feed,
    get_onboarding_state,
    get_top_agencies,
    record_milestone,
)
from app.services.onboarding import STEP_ORDER

router = APIRouter(tags=["welcome"])

PROGRESS_STEPS: List[Tuple[str, str]] = [
    ("signup", "Account Created"),
    ("browsing", "Find Opportunities"),
    ("tracked_first", "Track First Bid"),
    ("completed", "Set Up Alerts"),
]


@router.get("/welcome", response_class=HTMLResponse)
async def welcome_dashboard(request: Request):
    user_email = await require_login(request)

    onboarding = await get_onboarding_state(user_email)
    interest_key = onboarding.get("primary_interest") or DEFAULT_INTEREST_KEY
    profile = get_interest_profile(interest_key)

    # log that the user is browsing
    await record_milestone(user_email, "browsing", {"route": "/welcome"})

    feed_rows = await fetch_interest_feed(interest_key, limit=7)
    top_agencies = await get_top_agencies()

    progress_html = _render_progress(onboarding.get("onboarding_step") or "signup")
    cards_html = _render_cards(feed_rows)
    agency_pills = _render_agency_pills(top_agencies)

    interest_label_text = interest_label(interest_key)
    show_customize = not onboarding.get("onboarding_completed")

    customize_card = ""
    if show_customize:
        customize_card = """
        <section class="card hint-card">
            <div>
                <div class="mini-head">Want better matches?</div>
                <div class="mini-desc">Fine-tune agencies and email cadence in 60 seconds.</div>
            </div>
            <button id="open-quick-prefs" class="button-secondary" type="button">Customize Alerts</button>
        </section>
        """

    body_html = f"""
    <section class="card">
        <h1 class="section-heading">Welcome back</h1>
        <div class="mini-desc">Curated opportunities for <b>{html.escape(interest_label_text)}</b></div>
        {progress_html}
    </section>

    {customize_card}

    <section class="card">
        <div class="head-row">
            <h2 class="section-heading">Opportunities tailored to you</h2>
            <div class="muted">Tap Track to save into your bid tracker</div>
        </div>
        <div class="welcome-grid" id="welcome-grid">
            {cards_html or "<div class='muted'>No matching opportunities just yet. Adjust agencies to widen the net.</div>"}
        </div>
    </section>

    {_quick_preferences_modal(agency_pills)}
    {_celebration_modal()}
    <div id="welcome-toast" class="welcome-toast" hidden></div>

    
    <script>
    (function() {{
        const grid = document.getElementById('welcome-grid');
        const toastEl = document.getElementById('welcome-toast');
        const prefsModal = document.getElementById('quick-prefs-modal');
        const celebrationModal = document.getElementById('celebration-modal');

        function getCsrfToken() {{
            const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
            return match ? decodeURIComponent(match[1]) : '';
        }}

        function showToast(msg) {{
            if(!toastEl) return;
            toastEl.textContent = msg;
            toastEl.hidden = false;
            setTimeout(() => toastEl.hidden = true, 2500);
        }}

        function launchConfetti() {{
            const wrapper = document.createElement('div');
            wrapper.className = 'confetti-wrapper';
            const colors = ['#4f46e5', '#f97316', '#0ea5e9', '#10b981', '#f43f5e'];
            for(let i=0;i<30;i++) {{
                const piece = document.createElement('span');
                piece.className = 'confetti-piece';
                piece.style.setProperty('--left', Math.random()*100 + '%');
                piece.style.setProperty('--duration', (1.2 + Math.random()*0.8) + 's');
                piece.style.setProperty('--color', colors[i % colors.length]);
                wrapper.appendChild(piece);
            }}
            document.body.appendChild(wrapper);
            setTimeout(() => wrapper.remove(), 2000);
        }}

        function openCelebration() {{
            if(!celebrationModal) return;
            celebrationModal.classList.add('show');
            launchConfetti();
        }}

        function closeCelebration() {{
            if(!celebrationModal) return;
            celebrationModal.classList.remove('show');
        }}

        document.getElementById('celebration-close')?.addEventListener('click', () => {{
            closeCelebration();
            dismissOnboarding();
        }});
        document.getElementById('celebration-dashboard')?.addEventListener('click', () => {{
            dismissOnboarding();
            window.location.href = '/tracker/dashboard';
        }});
        document.getElementById('celebration-track-more')?.addEventListener('click', () => {{
            closeCelebration();
            dismissOnboarding();
        }});

        function dismissOnboarding() {{
            const csrf = getCsrfToken();
            fetch('/api/onboarding/dismiss', {{
                method:'POST',
                headers: csrf ? {{'X-CSRF-Token': csrf}} : undefined
            }}).catch(()=>{{}});
        }}

        grid?.addEventListener('click', async (event) => {{
            const btn = event.target.closest('.track-btn');
            if(!btn) return;
            const oppId = btn.dataset.oppId;
            const ext = btn.dataset.ext || '';
            btn.disabled = true;
            try {{
                const csrf = getCsrfToken();
                const res = await fetch(`/tracker/${{encodeURIComponent(oppId)}}/track`, {{
                    method: 'POST',
                    headers: Object.assign(
                        {{'Content-Type':'application/json'}},
                        csrf ? {{'X-CSRF-Token': csrf}} : {{}}
                    ),
                    body: ext ? JSON.stringify({{external_id: ext}}) : undefined
                }});
                if(res.ok) {{
                    btn.textContent = 'Tracked';
                    const payload = await res.json().catch(() => ({{}}));
                    if(payload.first_time) {{
                        openCelebration();
                    }} else {{
                        showToast('Bid tracked');
                    }}
                }} else {{
                    btn.disabled = false;
                    showToast('Unable to track right now');
                }}
            }} catch (err) {{
                btn.disabled = false;
                showToast('Network error');
            }}
        }});

        const openPrefsBtn = document.getElementById('open-quick-prefs');
        const closePrefsBtn = document.getElementById('close-quick-prefs');
        const skipPrefsBtn = document.getElementById('skip-quick-prefs');
        const prefsForm = document.getElementById('quick-prefs-form');

        function setPrefsModal(open) {{
            if(!prefsModal) return;
            prefsModal.classList.toggle('show', !!open);
        }}

        openPrefsBtn?.addEventListener('click', () => setPrefsModal(true));
        closePrefsBtn?.addEventListener('click', () => setPrefsModal(false));
        skipPrefsBtn?.addEventListener('click', () => {{
            setPrefsModal(false);
            dismissOnboarding();
        }});

        const agencyPills = Array.from(document.querySelectorAll('.agency-pill'));
        agencyPills.forEach((pill) => {{
            pill.addEventListener('click', () => {{
                pill.classList.toggle('active');
            }});
        }});

        prefsForm?.addEventListener('submit', async (event) => {{
            event.preventDefault();
            const selectedAgencies = agencyPills
                .filter((pill) => pill.classList.contains('active'))
                .map((pill) => pill.dataset.value);
            const freq = prefsForm.querySelector('input[name=\"frequency\"]:checked')?.value || 'weekly';
            try {{
                const csrf = getCsrfToken();
                const res = await fetch('/preferences/quick-setup', {{
                    method: 'POST',
                    headers: Object.assign(
                        {{'Content-Type':'application/json'}},
                        csrf ? {{'X-CSRF-Token': csrf}} : {{}}
                    ),
                    body: JSON.stringify({{agencies: selectedAgencies, frequency: freq}})
                }});
                if(res.ok) {{
                    showToast('Alerts updated');
                    setPrefsModal(false);
                    dismissOnboarding();
                }} else {{
                    showToast('Unable to save preferences');
                }}
            }} catch (err) {{
                showToast('Unable to save preferences');
            }}
        }});
    }})();
    </script>
    """

    return HTMLResponse(
        page_shell(
            body_html,
            title="Welcome  &middot;  EasyRFP",
            user_email=user_email,
        )
    )


def _render_progress(current_step: str) -> str:
    current_rank = STEP_ORDER.get(current_step, 0)
    items = []
    for step_key, label in PROGRESS_STEPS:
        rank = STEP_ORDER.get(step_key, 0)
        is_active = current_rank >= rank
        cls = "progress-step active" if is_active else "progress-step"
        badge = "&#10003;" if is_active else str(rank + 1)
        items.append(
            f"<div class='{cls}'><div class='progress-badge'>{badge}</div><div>{html.escape(label)}</div></div>"
        )
    return f"<div class='progress-track'>{''.join(items)}</div>"


def _render_cards(rows):
    def format_due(value):
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

    cards = []
    for row in rows:
        due = format_due(row.get("due_date"))
        summary = row.get("ai_summary") or row.get("summary") or "Summary is coming soon."
        summary = (summary[:180] + "...") if len(summary) > 183 else summary
        cards.append(
            f"""
            <article class="welcome-card" data-opp-id="{html.escape(str(row.get('id') or ''))}">
                <div class="mini-head">{html.escape(row.get('agency_name') or 'Agency TBD')}</div>
                <h3>{html.escape(row.get('title') or 'Untitled opportunity')}</h3>
                <div class="muted" style="font-size:12px;">{html.escape(row.get('category') or 'General')}  &middot;  Due {html.escape(due)}</div>
                <p class="summary">{html.escape(summary)}</p>
                <div class="card-actions">
                    <button class="button-primary track-btn" data-opp-id="{html.escape(str(row.get('id') or ''))}" data-ext="{html.escape(row.get('external_id') or '')}">Track this bid</button>
                    <a class="cta-link" href="/opportunity/{html.escape(str(row.get('id') or ''))}" target="_blank" rel="noopener">View full details</a>
                </div>
            </article>
            """
        )
    return "".join(cards)


def _render_agency_pills(rows) -> str:
    return "".join(
        f"<button type='button' class='agency-pill' data-value='{html.escape(row['agency'])}'>"
        f"{html.escape(row['agency'])} <span class='muted'>({row['count']})</span></button>"
        for row in rows
    )


def _quick_preferences_modal(agency_pills: str) -> str:
    return f"""
    <div class="modal-backdrop" id="quick-prefs-modal">
        <div class="modal-card">
            <button class="modal-close" id="close-quick-prefs" type="button">&times;</button>
            <h3 class="section-heading" style="margin-bottom:6px;">Quick preferences</h3>
            <div class="mini-desc">Pick a few agencies and when you want email alerts.</div>
            <form id="quick-prefs-form" style="margin-top:16px;">
                <label class="label-small">Agencies</label>
                <div class="pill-grid">
                    {agency_pills or "<div class='muted'>No agencies loaded yet.</div>"}
                </div>
                <label class="label-small" style="margin-top:18px;">Email frequency</label>
                <div class="freq-options">
                    <label><input type="radio" name="frequency" value="daily" checked> Daily</label>
                    <label><input type="radio" name="frequency" value="weekly"> Weekly</label>
                    <label><input type="radio" name="frequency" value="none"> Real-time (coming soon)</label>
                </div>
                <div class="card-actions" style="margin-top:18px;">
                    <button class="button-primary" type="submit">Save preferences</button>
                    <button class="button-secondary" type="button" id="skip-quick-prefs">Skip for now</button>
                </div>
            </form>
        </div>
    </div>
    """


def _celebration_modal() -> str:
    return """
    <div class="celebration-modal" id="celebration-modal">
        <div class="celebration-card">
            <button class="modal-close" id="celebration-close" type="button">&times;</button>
            <h2 class="section-heading">First bid tracked! &#127881;</h2>
            <p class="subtext">We just unlocked email updates, document uploads, and your bid tracker.</p>
            <div class="card-actions" style="justify-content:center;margin-top:16px;">
                <button class="button-primary" id="celebration-track-more" type="button">Track more bids</button>
                <button class="button-secondary" id="celebration-dashboard" type="button">See my dashboard</button>
            </div>
        </div>
    </div>
    """
