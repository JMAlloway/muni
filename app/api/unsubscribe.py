import uuid
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from app.core.db import AsyncSessionLocal
from app.core.unsubscribe import parse_unsubscribe_token
from app.api._layout import page_shell

router = APIRouter(tags=["unsubscribe"])

_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS digest_unsub_log (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    reason TEXT,
    user_agent TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(request: Request, token: str | None = None, email: str | None = None):
    """
    One-click unsubscribe from digest emails.
    Accepts a signed token in the URL and immediately sets digest_frequency='none'.
    """
    token_email = parse_unsubscribe_token(token)
    target_email = (token_email or email or "").strip().lower()
    if not target_email:
        body = "<section class='card'><h2 class='section-heading'>Unsubscribe link is invalid or expired.</h2></section>"
        return HTMLResponse(page_shell(body, title="Unsubscribe", user_email=None), status_code=400)

    async with AsyncSessionLocal() as session:
        # Log the request (best-effort)
        try:
            await session.execute(text(_LOG_TABLE_SQL))
            await session.execute(
                text(
                    """
                    INSERT INTO digest_unsub_log (id, email, reason, user_agent)
                    VALUES (:id, :email, :reason, :ua)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "email": target_email,
                    "reason": "one-click",
                    "ua": request.headers.get("user-agent", "")[:255],
                },
            )
        except Exception:
            # Do not block on logging failures
            pass

        # Update the user preference
        await session.execute(
            text(
                """
                UPDATE users
                SET digest_frequency = 'none'
                WHERE lower(email) = lower(:email)
                """
            ),
            {"email": target_email},
        )
        await session.commit()

    body = f"""
    <section class="card">
      <h2 class="section-heading">You're unsubscribed</h2>
      <p class="subtext">We stopped digest emails for <b>{target_email}</b>. You can resubscribe anytime in your preferences.</p>
      <a class="button-primary" href="/login">Go to EasyRFP</a>
    </section>
    """
    return HTMLResponse(page_shell(body, title="Unsubscribed", user_email=None))

