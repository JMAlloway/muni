# app/scheduler.py
import asyncio
from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Tuple
import json
from urllib.parse import quote_plus

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.core.settings import settings
from app.core.db_core import engine, save_opportunities
from app.core.db import AsyncSessionLocal  # legacy ORM session factory for users table
from app.core.emailer import send_email
from app.core.sms import send_sms
from app.ingest.runner import run_ingestors_once
from app.core.unsubscribe import build_unsubscribe_url


APP_BASE_URL = getattr(settings, "PUBLIC_APP_URL", "http://localhost:8000")



# --------------------------------------------------------------------------------------
# Helper: HTML email body builder
# --------------------------------------------------------------------------------------

def build_digest_html(
    grouped_by_agency: Dict[str, List[Tuple[str, str, str]]],
    total_count: int
) -> str:
    """
    grouped_by_agency looks like:
        {
          "City of Columbus": [
            ("Bucket Lift Upfit", "2025-11-13", "https://...#rfq=RFQ031498"),
            ("Pedestrian Safety Improvements ...", "2025-11-13", "https://..."),
            ...
          ],
          "Delaware County": [
            ...
          ]
        }

    total_count is total items in this personalized digest.
    """

    parts = []

    parts.append(
        "<div style='font-family:-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;"
        "max-width:600px;margin:0 auto;padding:16px 20px;color:#1a1a1a;'>"
        f"<h2 style='margin:0 0 12px;font-size:20px;font-weight:600;'>"
        f"EasyRFP - {total_count} New / Updated Opportunities"
        "</h2>"
        "<p style='margin:0 0 24px;font-size:14px;line-height:1.4;color:#444;'>"
        "Bids and RFPs sourced from participating municipalities in Central Ohio."
        "</p>"
    )

    for agency_name, items in grouped_by_agency.items():
        parts.append(
            f"<h3 style='margin:0 0 8px;font-size:16px;font-weight:600;color:#111;'>{agency_name}</h3>"
            "<ul style='margin:0 0 24px;padding-left:18px;font-size:14px;line-height:1.4;color:#222;'>"
        )

        for title, due_str, url in items:
            parts.append(
                "<li style='margin-bottom:8px;'>"
                f"<b style='font-weight:600;color:#000;'>{title}</b><br>"
                f"<span style='color:#555;'>Due: {due_str} · "
                f"<a href='{url}' style='color:#1a73e8;text-decoration:underline;'>View</a>"
                "</span>"
                "</li>"
            )

        parts.append("</ul>")

    parts.append(
        "<hr style='border:none;border-top:1px solid #ddd;margin:24px 0;'>"
        "<p style='margin:0;font-size:12px;line-height:1.4;color:#777;'>"
        "You're receiving this because you're subscribed to EasyRFP. "
        "Preferences (frequency, agencies, etc.) coming soon.<br>"
        "<span style='color:#bbb;'>Prototype build • not for redistribution</span>"
        "</p>"
        "</div>"
    )

    return "".join(parts)


# --------------------------------------------------------------------------------------
# Job: scrape all sources and persist opportunities
# --------------------------------------------------------------------------------------

async def job_scrape():
    """
    Run all ingestors and persist opportunities.
    This calls the same logic as python -m app.ingest.runner.
    """
    print("[job_scrape] starting")
    processed = await run_ingestors_once()
    print(f"[job_scrape] done. processed={processed}")


# --------------------------------------------------------------------------------------
# Internal helpers for digest jobs (daily & weekly share these)
# --------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------
# Internal helpers for digest jobs (daily & weekly share these)
# --------------------------------------------------------------------------------------

async def _collect_recent_opportunities(since_dt: datetime):
    """
    Query all opportunities updated since `since_dt`.
    Returns:
        by_agency_all: { agency_name: [row_dict, ...] }
        raw_rows_count: total rows seen in that window
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT id,
                    external_id,
                    agency_name,
                    title,
                    due_date,
                    source_url,
                    ai_summary,
                    ai_tags_json,
                    ai_category,
                    updated_at
                FROM opportunities
                WHERE updated_at >= :since
                AND status = 'open'
                ORDER BY agency_name, due_date
            """),
            {"since": since_dt},
        )
        rows = [dict(r) for r in result.mappings().all()]


    by_agency_all: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        agency_key = r.get("agency_name") or "Other"
        by_agency_all.setdefault(agency_key, []).append(r)

    return by_agency_all, len(rows)


async def _send_digest_to_matching_users(
    db,
    target_frequency: str,
    by_agency_all: dict[str, list[dict]],
):
    """
    Build and send enriched digest emails with AI summaries + tags.
    """
    res = await db.execute(
        text("""
            SELECT email,
                   digest_frequency,
                   agency_filter,
                   tier,
                   sms_phone,
                   sms_opt_in,
                   sms_phone_verified
            FROM users
            WHERE is_active = 1
        """)
    )
    users = res.fetchall()
    total_sent = 0
    total_opps_count = sum(len(v) for v in by_agency_all.values())
    window_text = "the last 24 hours" if target_frequency == "daily" else "the last 7 days"

    print("[digest] cooling down to satisfy Mailtrap rate limits...")
    await asyncio.sleep(2.0)

    for row in users:
        (
            email,
            freq,
            agency_filter_json,
            tier,
            sms_phone,
            sms_opt_in,
            sms_phone_verified,
        ) = row
        freq_norm = (freq or "").strip().lower()
        if not freq_norm:
            # No preference set: default to weekly
            freq_norm = "weekly"
        if freq_norm in {"none", "off", "unsubscribed", "unsubscribe"}:
            continue
        if freq_norm != target_frequency:
            continue

        # parse agency filter JSON
        try:
            agency_filter = json.loads(agency_filter_json or "[]")
            if not isinstance(agency_filter, list):
                agency_filter = []
        except Exception:
            agency_filter = []

        agencies_for_user = (
            [a for a in by_agency_all.keys() if a in agency_filter]
            if agency_filter else list(by_agency_all.keys())
        )
        if not agencies_for_user:
            continue

        agency_sections_html = []

        for agency_name in sorted(agencies_for_user):
            items = by_agency_all.get(agency_name, [])
            if not items:
                continue

            section = [f"<h3 style='font-size:16px;font-weight:600;color:#111;margin:24px 0 12px;'>{agency_name}</h3>"]
            for r in items:
                title = r.get("title") or "(no title)"
                due = r.get("due_date")
                due_str = str(due).split(" ")[0] if due else "TBD"
                summary = r.get("ai_summary") or ""
                agency_name = r.get("agency_name") or ""
                try:
                    tags = json.loads(r.get("ai_tags_json") or "[]")
                except Exception:
                    tags = []

                # --- build link back to /opportunities with filters ---
                opp_id = r.get("id")
                ext_id = r.get("external_id")
                source_url = r.get("source_url") or "#"

                if ext_id:
                    # this is the main path for your COTA etc.
                    detail_url = (
                        f"{APP_BASE_URL}/opportunities?"
                        f"ext={quote_plus(ext_id)}&agency={quote_plus(agency_name)}"
                    )
                elif opp_id:
                    # backup: if we only have internal id
                    detail_url = (
                        f"{APP_BASE_URL}/opportunities?"
                        f"id={quote_plus(str(opp_id))}&agency={quote_plus(agency_name)}"
                    )
                else:
                    # last resort: original source
                    detail_url = source_url

                # --- HTML block ---
                section.append("<div style='margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #eee;'>")
                section.append(
                    f"<a href='{detail_url}' style='font-weight:600;color:#0366d6;text-decoration:none;'>{title}</a>"
                )
                section.append(f"<div style='font-size:12px;color:#666;'>Due: {due_str}</div>")
                if summary:
                    section.append(f"<p style='margin:4px 0;font-size:13px;color:#333;'>{summary}</p>")
                if tags:
                    chips = ' '.join(
                        f"<span style='display:inline-block;background:#eef;border-radius:4px;"
                        f"padding:2px 6px;margin:0 4px 4px 0;font-size:11px;color:#334;'>{t}</span>"
                        for t in tags
                    )
                    section.append(f"<div>{chips}</div>")
                section.append("</div>")

            agency_sections_html.append(''.join(section))

        if not agency_sections_html:
            continue

        unsubscribe_url = build_unsubscribe_url(email)
        html_body = (
            "<div style='font-family:Arial,sans-serif;color:#111;font-size:15px;line-height:1.5;"
            "background-color:#ffffff;padding:24px;max-width:640px;margin:auto;'>"
            f"<h2 style='margin:0 0 8px;font-size:20px;font-weight:600;'>"
            f"EasyRFP - {total_opps_count} New / Updated Opportunities</h2>"
            f"<p style='margin:0 0 24px;color:#4b5563;'>Bids and RFPs from {window_text}.</p>"
            + "".join(agency_sections_html) +
            "<hr style='border:none;border-top:1px solid #ddd;margin:24px 0;'>"
            "<p style='font-size:12px;color:#888;'>"
            "You're receiving this because you're subscribed to EasyRFP.<br>"
            f"<a href='{unsubscribe_url}' style='color:#1a73e8;'>Unsubscribe instantly</a> or "
            "adjust your preferences."
            "</p>"
            "</div>"
        )

        subject = f"EasyRFP - {total_opps_count} New / Updated Opportunities"

        try:
            await asyncio.to_thread(send_email, email, subject, html_body)
            print(f"[digest:{target_frequency}] sent to {email}")
            total_sent += 1
        except Exception as e:
            print(f"[digest:{target_frequency}] ERROR sending to {email}: {e}")

        # Optional SMS nudge for premium, opted-in, verified users
        premium_tiers = {"starter", "professional", "enterprise"}
        phone = (sms_phone or "").strip()
        if (
            phone
            and sms_opt_in
            and sms_phone_verified
            and (tier or "").lower() in premium_tiers
        ):
            sms_body = (
                f"{total_opps_count} new/updated bids in {window_text}. "
                f"See your feed: {APP_BASE_URL}/opportunities"
            )
            try:
                await asyncio.to_thread(send_sms, phone, sms_body)
            except Exception as exc:
                print(f"[digest:{target_frequency}] SMS failed for {email}: {exc}")

        await asyncio.sleep(2.0)

    return total_sent


# --------------------------------------------------------------------------------------
# Daily + Weekly jobs
# --------------------------------------------------------------------------------------

async def job_daily_digest():
    """
    Build and send the daily digest.
    Logic:
    - Look back 24h for any new/updated opportunities.
    - Group them by agency.
    - Send to all users with digest_frequency='daily'.
    """
    print("[job_daily_digest] starting")

    since = datetime.utcnow() - timedelta(days=1)

    by_agency_all, row_count = await _collect_recent_opportunities(since)

    if row_count == 0:
        print("[job_daily_digest] no new opportunities in ~24h")
        return {"sent": 0, "note": "no new opps"}

    async with AsyncSessionLocal() as db:
        sent_count = await _send_digest_to_matching_users(
            db,
            target_frequency="daily",
            by_agency_all=by_agency_all,
        )

    print(f"[job_daily_digest] done, sent {sent_count} emails")
    return {"sent": sent_count, "note": "daily digest complete"}


async def job_weekly_digest():
    """
    Build and send the weekly digest.
    Logic:
    - Look back 7 days for any new/updated opportunities.
    - Group them by agency.
    - Send to all users with digest_frequency='weekly'.
    """
    print("[job_weekly_digest] starting")

    since = datetime.utcnow() - timedelta(days=7)

    by_agency_all, row_count = await _collect_recent_opportunities(since)

    if row_count == 0:
        print("[job_weekly_digest] no new opportunities in ~7d")
        return {"sent": 0, "note": "no new opps"}

    async with AsyncSessionLocal() as db:
        sent_count = await _send_digest_to_matching_users(
            db,
            target_frequency="weekly",
            by_agency_all=by_agency_all,
        )

    print(f"[job_weekly_digest] done, sent {sent_count} emails")
    return {"sent": sent_count, "note": "weekly digest complete"}


# --------------------------------------------------------------------------------------
# Due-date reminders (7/3/1 days)
# --------------------------------------------------------------------------------------

_DUE_REMINDER_LOG_SQL = """
CREATE TABLE IF NOT EXISTS due_reminder_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    opportunity_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    due_date TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, opportunity_id, stage)
)
"""


async def _ensure_due_reminder_table():
    async with engine.begin() as conn:
        await conn.execute(text(_DUE_REMINDER_LOG_SQL))


async def job_due_date_reminders():
    """
    Send reminders at 7/3/1 days before due date for tracked opportunities.
    Skips users who have digest_frequency 'none'/'off'.
    """
    print("[job_due_date_reminders] starting")
    await _ensure_due_reminder_table()

    today = datetime.utcnow().date()
    max_day = today + timedelta(days=7)

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text(
                """
                SELECT
                    t.user_id,
                    u.email,
                    t.opportunity_id,
                    o.title,
                    o.agency_name,
                    o.due_date,
                    o.external_id,
                    o.id AS oid
                FROM user_bid_trackers t
                JOIN users u ON u.id = t.user_id
                JOIN opportunities o ON o.id = t.opportunity_id
                WHERE o.status = 'open'
                  AND o.due_date IS NOT NULL
                  AND DATE(o.due_date) BETWEEN DATE(:today) AND DATE(:max_day)
            """
            ),
            {"today": today.isoformat(), "max_day": max_day.isoformat()},
        )
        rows = [dict(r) for r in res.mappings().all()]

        for r in rows:
            due_val = r.get("due_date")
            try:
                due_date = due_val.date() if hasattr(due_val, "date") else datetime.fromisoformat(str(due_val)).date()
            except Exception:
                continue
            days_out = (due_date - today).days
            if days_out not in {1, 3, 7}:
                continue

            # Honor user opt-out (reuse digest_frequency as global preference)
            freq_res = await db.execute(
                text("SELECT digest_frequency FROM users WHERE id = :uid LIMIT 1"),
                {"uid": r["user_id"]},
            )
            freq_val = (freq_res.scalar() or "").lower()
            if freq_val in {"none", "off", "unsubscribe", "unsubscribed"}:
                continue

            stage = f"due_{days_out}"
            already = await db.execute(
                text(
                    """
                    SELECT 1 FROM due_reminder_log
                    WHERE user_id = :uid AND opportunity_id = :oid AND stage = :stage
                    LIMIT 1
                    """
                ),
                {"uid": r["user_id"], "oid": r["opportunity_id"], "stage": stage},
            )
            if already.scalar():
                continue

            detail_url = f"{APP_BASE_URL}/opportunities?ext={quote_plus(str(r.get('external_id') or r.get('oid')))}"
            title = r.get("title") or "Opportunity"
            agency = r.get("agency_name") or ""
            due_str = due_date.isoformat()

            html_body = (
                "<div style='font-family:Arial,sans-serif;color:#111;font-size:15px;line-height:1.5;"
                "background-color:#ffffff;padding:20px;max-width:620px;margin:auto;'>"
                f"<h3 style='margin:0 0 12px;font-size:18px;font-weight:700;'>Due in {days_out} day"
                f"{'' if days_out == 1 else 's'}: {title}</h3>"
                f"<p style='margin:0 0 8px;color:#4b5563;'>Agency: {agency}</p>"
                f"<p style='margin:0 0 8px;color:#4b5563;'>Due date: {due_str}</p>"
                f"<p style='margin:12px 0;'><a href='{detail_url}' style='color:#1a73e8;font-weight:600;'>View opportunity</a></p>"
                f"<p style='font-size:12px;color:#888;'>To stop due-date reminders, set your alerts to 'None' in preferences or unsubscribe from digests.</p>"
                "</div>"
            )

            try:
                await asyncio.to_thread(
                    send_email,
                    r["email"],
                    f"Reminder: {title} due in {days_out} days",
                    html_body,
                )
                await db.execute(
                    text(
                        """
                        INSERT INTO due_reminder_log (id, user_id, opportunity_id, stage, due_date)
                        VALUES (:id, :uid, :oid, :stage, :due)
                        ON CONFLICT(user_id, opportunity_id, stage) DO NOTHING
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "uid": r["user_id"],
                        "oid": r["opportunity_id"],
                        "stage": stage,
                        "due": due_str,
                    },
                )
                await db.commit()
            except Exception as exc:
                print(f"[job_due_date_reminders] failed for {r.get('email')} oid={r.get('opportunity_id')}: {exc}")
                await db.rollback()


# --------------------------------------------------------------------------------------
# APScheduler configuration
# --------------------------------------------------------------------------------------

scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)


def start_scheduler():
    """
    Register recurring jobs and start the scheduler.
    - Scrape every 2 hours on the hour
    - Daily digest every day at DIGEST_SEND_HOUR
    - Weekly digest every Friday at 07:00 (local time)
    """

    # Scrape all ingestors every 2 hours (awaited by AsyncIOScheduler)
    scheduler.add_job(
        job_scrape,
        CronTrigger(hour="*/2", minute=0),
        name="scrape_ingestors",
    )

    # Daily digest job
    scheduler.add_job(
        job_daily_digest,
        CronTrigger(hour=settings.DIGEST_SEND_HOUR, minute=0),
        name="daily_digest",
    )

    # Weekly digest job (Friday 7:00am local time)
    scheduler.add_job(
        job_weekly_digest,
        CronTrigger(day_of_week="fri", hour=7, minute=0),
        name="weekly_digest",
    )

    # Due-date reminders (daily, morning)
    scheduler.add_job(
        job_due_date_reminders,
        CronTrigger(hour=7, minute=30),
        name="due_date_reminders",
    )

    scheduler.start()
    print("[scheduler] started.")


# --------------------------------------------------------------------------------------
# Standalone runner mode (optional for debugging)
# --------------------------------------------------------------------------------------

if __name__ == "__main__":
    async def runner():
        start_scheduler()
        print("[main] scheduler running. Ctrl+C to stop.")
        # keep the loop alive forever
        while True:
            await asyncio.sleep(3600)

    asyncio.run(runner())
