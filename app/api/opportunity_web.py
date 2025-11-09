# app/routers/opportunity_web.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from app.core.db_core import engine

router = APIRouter(prefix="/opportunity", tags=["opportunity"])


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 760px;
      margin: 0 auto;
      padding: 20px 16px 40px 16px;
      background: #f7f7f7;
    }}
    .card {{
      background: #fff;
      border-radius: 10px;
      padding: 18px 20px 20px 20px;
      box-shadow: 0 10px 25px rgba(15, 23, 42, 0.06);
      margin-top: 20px;
    }}
    .chips span {{
      display: inline-block;
      background: #eef;
      border-radius: 999px;
      padding: 4px 10px;
      margin: 0 6px 6px 0;
      font-size: 12px;
      color: #334;
    }}
    a.source {{
      display: inline-block;
      margin-top: 14px;
      color: #0366d6;
      text-decoration: none;
      font-weight: 500;
    }}
    .muted {{
      color: #666;
      font-size: 13px;
      margin-bottom: 10px;
    }}
  </style>
</head>
<body>
  <h1 style="margin-top:0;">{title}</h1>
  <p class="muted">Agency: {agency} · Due: {due}</p>

  <div class="card">
    <h2 style="margin-top:0;font-size:16px;">Summary</h2>
    <p>{summary}</p>

    {tags_html}

    {source_html}
  </div>

</body>
</html>
"""


async def _fetch_opportunity_by_id(opp_id: str):
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, external_id, agency_name, title, due_date,
                       source_url, ai_summary, ai_tags_json
                FROM opportunities
                WHERE id = :id
                """
            ),
            {"id": opp_id},
        )
        row = result.mappings().first()
    return row


async def _fetch_opportunity_by_external_id(ext_id: str):
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, external_id, agency_name, title, due_date,
                       source_url, ai_summary, ai_tags_json
                FROM opportunities
                WHERE external_id = :ext
                """
            ),
            {"ext": ext_id},
        )
        row = result.mappings().first()
    return row


@router.get("/{opp_id}", response_class=HTMLResponse)
async def get_opportunity(opp_id: str):
    row = await _fetch_opportunity_by_id(opp_id)
    if not row:
        # try by external_id too, in case your ID is actually external_id
        row = await _fetch_opportunity_by_external_id(opp_id)
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    title = row.get("title") or "(no title)"
    agency = row.get("agency_name") or "Unknown agency"
    due = row.get("due_date") or "TBD"
    summary = row.get("ai_summary") or "No AI summary was generated for this opportunity."
    source_url = row.get("source_url") or ""
    tags_json = row.get("ai_tags_json") or "[]"

    # build tag chips
    try:
        import json
        tags = json.loads(tags_json)
    except Exception:
        tags = []

    if tags:
        tags_html = '<div class="chips">' + "".join(f"<span>{t}</span>" for t in tags) + "</div>"
    else:
        tags_html = ""

    if source_url:
        source_html = f'<a class="source" href="{source_url}" target="_blank" rel="noopener">View original source</a>'
    else:
        source_html = ""

    html = HTML_TEMPLATE.format(
        title=title,
        agency=agency,
        due=due,
        summary=summary,
        tags_html=tags_html,
        source_html=source_html,
    )
    return HTMLResponse(content=html)


@router.get("/by-external/{ext_id}", response_class=HTMLResponse)
async def get_opportunity_by_external(ext_id: str):
    row = await _fetch_opportunity_by_external_id(ext_id)
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # reuse handler above
    return await get_opportunity(row["id"])
