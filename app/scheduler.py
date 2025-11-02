# app/scheduler.py

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.settings import settings
from app.db_core import engine, save_opportunities
from app.db import AsyncSessionLocal  # legacy ORM session factory for users table
from app.emailer import send_email
from app.ingest.runner import run_ingestors_once


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
        f"Muni Alerts – {total_count} New / Updated Opportunities"
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
        "You’re receiving this because you're subscribed to Muni Alerts. "
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

async def _collect_recent_opportunities(since_dt: datetime):
    """
    Query all opportunities updated since `since_dt`.
    Returns:
        by_agency_all: { agency_name: [(title, due_str, url), ...] }
        raw_rows_count: total rows seen in that window
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT agency_name,
                       title,
                       due_date,
                       source_url,
                       updated_at
                FROM opportunities
                WHERE updated_at >= :since
                ORDER BY agency_name, due_date
            """),
            {"since": since_dt},
        )
        rows = result.fetchall()

    by_agency_all: Dict[str, List[Tuple[str, str, str]]] = {}

    for agency, title, due, url, updated_at in rows:
        agency_key = agency or "Other"

        # Normalize due date across SQLite (string) vs Postgres (datetime)
        if due:
            if hasattr(due, "strftime"):
                due_str = due.strftime("%Y-%m-%d")
            else:
                due_str = str(due).split(" ")[0]
        else:
            due_str = "TBD"

        by_agency_all.setdefault(agency_key, []).append((title, due_str, url))

    return by_agency_all, len(rows)


async def _send_digest_to_matching_users(
    db,
    target_frequency: str,
    by_agency_all: dict[str, list[tuple[str, str, str]]],
):
    """
    Build the simple contractor-friendly digest:
    - Header: "Muni Alerts — {N} New / Updated Opportunities"
    - Subheader: "Bids and RFPs from the last 24 hours..."
    - For each agency:
        • <bold title>
          Due: <due> · View
    Throttles between sends to avoid Mailtrap rate limiting.
    """

    # 1. Get list of active users
    res = await db.execute(
        text("""
            SELECT email,
                   digest_frequency,
                   agency_filter
            FROM users
            WHERE is_active = 1
        """)
    )
    users = res.fetchall()

    total_sent = 0

    # 2. How many total opps are we reporting?
    total_opps_count = sum(len(v) for v in by_agency_all.values())

    # 3. Wording for the timeframe based on digest type
    if target_frequency.strip().lower() == "daily":
        window_text = "the last 24 hours"
    else:
        window_text = "the last 7 days"

    # 4. Give Mailtrap a breather before first send
    print("[digest] cooling down to satisfy Mailtrap rate limits...")
    await asyncio.sleep(2.0)

    # 5. Send to each user
    for row in users:
        email, freq, agency_filter_json = row

        # skip users not on this schedule
        if (freq or "").strip().lower() != target_frequency:
            continue

        # parse stored agency_filter (JSON array of agency names)
        try:
            agency_filter = json.loads(agency_filter_json or "[]")
            if not isinstance(agency_filter, list):
                agency_filter = []
        except Exception:
            agency_filter = []

        # pick agencies for this user
        if agency_filter:
            agencies_for_user = [a for a in by_agency_all.keys() if a in agency_filter]
        else:
            agencies_for_user = list(by_agency_all.keys())

        if not agencies_for_user:
            continue

        # 6. Build HTML sections per agency for this user
        agency_sections_html = []

        for agency_name in sorted(agencies_for_user):
            bids_for_agency = by_agency_all.get(agency_name, [])
            if not bids_for_agency:
                continue

            bid_list_items = []
            for bid_tuple in bids_for_agency:
                # IMPORTANT: this matches _collect_recent_opportunities
                # bid_tuple = (title, due_str, url)
                title_val = bid_tuple[0] if len(bid_tuple) > 0 else ""
                due_val   = bid_tuple[1] if len(bid_tuple) > 1 else "TBD"
                url_val   = bid_tuple[2] if len(bid_tuple) > 2 else "#"

                bid_list_items.append(
                    "<li style='margin:0 0 14px 0; padding:0;'>"
                    f"<div style='font-size:15px; font-weight:600; color:#111; line-height:1.4;'>"
                    f"{title_val}</div>"
                    "<div style='font-size:13px; color:#4b5563; line-height:1.4; margin-top:2px;'>"
                    f"Due: {due_val} · "
                    f"<a href='{url_val}' style='color:#1a56db; text-decoration:underline;'>View</a>"
                    "</div>"
                    "</li>"
                )

            if not bid_list_items:
                continue

            agency_sections_html.append(
                f"<h3 style='font-size:16px; font-weight:600; color:#111; "
                f"margin:24px 0 12px 0; line-height:1.4;'>{agency_name}</h3>"
                "<ul style='margin:0; padding-left:20px; list-style:disc;'>"
                + "".join(bid_list_items) +
                "</ul>"
            )

        if not agency_sections_html:
            continue

        # 7. Wrap the whole email body in the “nice” layout you liked
        html_body = (
            "<div style='font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,"
            "Helvetica,Arial,sans-serif; color:#111; font-size:15px; "
            "line-height:1.5; background-color:#ffffff; padding:24px;'>"

            f"<div style='font-size:20px; font-weight:600; color:#111; margin:0 0 8px 0;'>"
            f"Muni Alerts — {total_opps_count} New / Updated Opportunities</div>"

            "<div style='font-size:14px; color:#4b5563; margin:0 0 24px 0; line-height:1.5;'>"
            f"Bids and RFPs from {window_text} in your selected municipalities."
            "</div>"

            + "".join(agency_sections_html) +

            "<hr style='border:none; border-top:1px solid #e5e7eb; margin:32px 0 16px;'/>"

            "<div style='font-size:12px; color:#6b7280; line-height:1.4;'>"
            "You’re getting these alerts because you asked Muni Alerts to watch these agencies. "
            "To change frequency or unsubscribe, update your preferences."
            "</div>"

            "</div>"
        )

        # 8. Subject line consistent with the header
        subject = f"Muni Alerts — {total_opps_count} New / Updated Opportunities"

        # 9. Send, with throttling so Mailtrap doesn't rate limit
        try:
            await asyncio.to_thread(send_email, email, subject, html_body)
            print(f"[digest:{target_frequency}] sent to {email}")
            total_sent += 1
        except Exception as e:
            print(f"[digest:{target_frequency}] ERROR sending to {email}: {e}")

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

    # Scrape all ingestors every 2 hours
    scheduler.add_job(
        lambda: asyncio.create_task(job_scrape()),
        CronTrigger(hour="*/2", minute=0),
        name="scrape_ingestors",
    )

    # Daily digest job
    scheduler.add_job(
        lambda: asyncio.create_task(job_daily_digest()),
        CronTrigger(hour=settings.DIGEST_SEND_HOUR, minute=0),
        name="daily_digest",
    )

    # Weekly digest job (Friday 7:00am local time)
    scheduler.add_job(
        lambda: asyncio.create_task(job_weekly_digest()),
        CronTrigger(day_of_week="fri", hour=7, minute=0),
        name="weekly_digest",
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
