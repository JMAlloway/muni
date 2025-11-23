# app/email_digest.py
import json
import sys
from pathlib import Path
from sqlalchemy import text

from app.core.db_core import engine
from app.core.emailer import send_email
from app.ai.client import get_llm_client


async def build_digest_html(conn, llm_client=None) -> str:
    """Build HTML digest using AI summaries and tags."""
    result = await conn.execute(
        text("""
            SELECT agency_name,
                   title,
                   source_url,
                   due_date,
                   ai_summary,
                   ai_tags_json,
                   ai_category
            FROM opportunities
            WHERE status = 'open'
            ORDER BY agency_name, due_date
        """)
    )
    rows = [dict(r) for r in result.mappings().all()]

    # group by agency
    grouped = {}
    for r in rows:
        grouped.setdefault(r["agency_name"], []).append(r)

    html = [
        "<html><body style='font-family:Arial,sans-serif;'>",
        "<h1 style='margin-bottom:16px;'>EasyRFP - New Opportunities</h1>",
    ]

    for agency, items in grouped.items():
        html.append(f"<h2 style='margin-top:24px;color:#222;'>{agency}</h2>")

        # optional AI intro using LLM
        if llm_client and items:
            titles = "\n".join(f"- {i['title']}" for i in items[:6])
            prompt = (
                f"Summarize these municipal RFPs from {agency} in one short paragraph:\n"
                f"{titles}\n\nLimit to 45 words, plain language."
            )
            try:
                resp = llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0,
                )
                resp = (resp or "").strip()
                if resp:
                    html.append(f"<p style='color:#555;font-size:13px;margin:4px 0 12px 0;'>{resp}</p>")
            except Exception as e:
                print(f"[digest intro error] {e}")

        for r in items:
            title = r["title"] or "(no title)"
            due = r["due_date"] or "TBD"
            url = r["source_url"] or "#"
            summary = r.get("ai_summary") or ""
            try:
                tags = json.loads(r.get("ai_tags_json") or "[]")
            except Exception:
                tags = []

            html.append("<div style='margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #eee;'>")
            html.append(
                f"<a href='{url}' style='font-weight:600;color:#0366d6;text-decoration:none;'>{title}</a>"
            )
            html.append(f"<div style='font-size:12px;color:#666;'>Due: {due}</div>")
            if summary:
                html.append(
                    f"<p style='margin:4px 0 4px 0;font-size:13px;color:#333;'>{summary}</p>"
                )
            if tags:
                chips = " ".join(
                    f"<span style='display:inline-block;background:#eef;border-radius:4px;"
                    f"padding:2px 6px;margin:0 4px 4px 0;font-size:11px;color:#334;'>{t}</span>"
                    for t in tags
                )
                html.append(f"<div>{chips}</div>")
            html.append("</div>")

    html.append("</body></html>")
    return "".join(html)


async def send_digest(to_email: str):
    """Build and send AI-enriched digest."""
    llm_client = get_llm_client()
    async with engine.begin() as conn:
        html = await build_digest_html(conn, llm_client=llm_client)
    subject = "EasyRFP - New Opportunities"
    send_email(to_email, subject, html)
    print(f"✅ Digest sent to {to_email}")


async def preview_digest(outfile: str = "digest_preview.html"):
    """Build digest and write to a local HTML file (no email)."""
    llm_client = get_llm_client()
    async with engine.begin() as conn:
        html = await build_digest_html(conn, llm_client=llm_client)

    outpath = Path(outfile).resolve()
    outpath.write_text(html, encoding="utf-8")
    print(f"📝 Preview written to {outpath}")


if __name__ == "__main__":
    import asyncio

    # CLI:
    #   python -m app.email_digest you@example.com
    #   python -m app.email_digest --preview
    #   python -m app.email_digest --preview out.html
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python -m app.email_digest you@example.com")
        print("  python -m app.email_digest --preview [outfile]")
        raise SystemExit(1)

    if args[0] == "--preview":
        outfile = args[1] if len(args) > 1 else "digest_preview.html"
        asyncio.run(preview_digest(outfile))
    else:
        # treat first arg as email
        to_email = args[0]
        asyncio.run(send_digest(to_email))
