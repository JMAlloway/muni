import uuid
from datetime import datetime
from urllib.parse import quote_plus

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.core.calendar_token import parse_calendar_token, make_calendar_token
from app.core.settings import settings

router = APIRouter(tags=["calendar"])

APP_BASE_URL = getattr(settings, "PUBLIC_APP_URL", "http://localhost:8000")


def _ical_escape(val: str) -> str:
    return (
        val.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _build_ics(email: str, rows: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EasyRFP//Calendar//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:EasyRFP Due Dates ({email})",
    ]
    for r in rows:
        due = r.get("due_date")
        if not due:
            continue
        try:
            due_date = due.date() if hasattr(due, "date") else datetime.fromisoformat(str(due)).date()
        except Exception:
            continue
        uid = f"{r.get('id')}-{email}"
        title = r.get("title") or "Opportunity due"
        agency = r.get("agency_name") or ""
        ext = r.get("external_id") or r.get("id")
        detail_url = f"{APP_BASE_URL}/opportunities?ext={quote_plus(str(ext))}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ical_escape(uid)}",
                f"SUMMARY:{_ical_escape(title)}",
                f"DESCRIPTION:{_ical_escape(f'{agency} — Due soon. View: {detail_url}')}",
                f"DTSTART;VALUE=DATE:{due_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(due_date).strftime('%Y%m%d')}",
                f"URL:{_ical_escape(detail_url)}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


@router.get("/calendar.ics", response_class=PlainTextResponse)
async def calendar_feed(request: Request, token: str | None = None):
    """
    iCal feed of tracked opportunities' due dates.
    Accepts a signed token (?token=...) or falls back to the current session user.
    """
    email = parse_calendar_token(token)
    if not email:
        email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT o.id, o.title, o.agency_name, o.due_date, o.external_id
            FROM user_bid_trackers t
            JOIN users u ON u.id = t.user_id
            JOIN opportunities o ON o.id = t.opportunity_id
            WHERE lower(u.email) = lower(:email)
              AND o.due_date IS NOT NULL
              AND o.status = 'open'
            ORDER BY o.due_date ASC
            """,
            {"email": email},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    ics = _build_ics(email, rows)
    headers = {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Disposition": 'attachment; filename="easyrfp-calendar.ics"',
    }
    return PlainTextResponse(ics, media_type="text/calendar", headers=headers)


@router.get("/api/calendar/token", response_class=PlainTextResponse)
async def issue_calendar_token(request: Request):
    """
    Return a signed calendar token for the current user.
    """
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return PlainTextResponse(make_calendar_token(email))

