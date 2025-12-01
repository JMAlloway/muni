        # Track button: use data-* (no inline JS)

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
import math
import json
import datetime as dt

from app.core.db_core import engine
from app.api._layout import page_shell
from app.auth.auth_utils import require_login
from app.data.agencies import AGENCIES

TEMPLATE_DIR = Path(__file__).parent / "templates" / "opportunities"


def render_template(name: str, context: dict[str, str] | None = None) -> str:
    content = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    if not context:
        return content
    for key, value in context.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities", response_class=HTMLResponse)
async def opportunities(request: Request):
    # -------- auth --------
    user_email = await require_login(request)
    if isinstance(user_email, RedirectResponse):
        return user_email

    user_id = None
    async with engine.begin() as conn:
        uid_res = await conn.execute(
            text("SELECT id FROM users WHERE lower(email) = lower(:email) LIMIT 1"),
            {"email": user_email},
        )
        uid_row = uid_res.first()
        if uid_row:
            user_id = uid_row[0]

    query_params = request.query_params

    # -------- pagination --------
    try:
        page = int(query_params.get("page", "1"))
    except ValueError:
        page = 1
    if page < 1:
        page = 1

    page_size = 25
    offset = (page - 1) * page_size

    # -------- filters from querystring --------
    agency_param_present = "agency" in query_params
    agency_filter = query_params.get("agency", "").strip()
    search_filter = query_params.get("search", "").strip()
    due_within_raw = query_params.get("due_within", "").strip()
    sort_by = query_params.get("sort_by", "soonest_due").strip()
    status_vals = query_params.getlist("status") if hasattr(query_params, "getlist") else []
    if not status_vals:
        status_vals = [query_params.get("status", "open")]
    raw_status = (status_vals[-1] or "").strip().lower()
    status_filter = "" if raw_status in {"", "all", "any"} else raw_status

    # -------- saved preferences (agencies, keywords) --------
    pref_agencies = []
    pref_keywords = []
    async with engine.begin() as conn:
        pref_res = await conn.execute(
            text("SELECT agencies, keywords FROM user_preferences WHERE user_email = :email"),
            {"email": user_email},
        )
        pref_row = pref_res.first()
    if pref_row:
        try:
            pref_agencies = json.loads(pref_row[0] or "[]") if len(pref_row) > 0 else []
        except Exception:
            pref_agencies = []
        try:
            pref_keywords = json.loads(pref_row[1] or "[]") if len(pref_row) > 1 else []
        except Exception:
            pref_keywords = []

    # fallback to saved preference if no agency specified in URL
    if not agency_param_present and not agency_filter and pref_agencies:
        agency_filter = pref_agencies[0]

    # normalize due_within
    allowed_due_windows = {"7", "30", "90"}
    if due_within_raw in allowed_due_windows:
        due_within = int(due_within_raw)
    else:
        due_within = None

    # normalize sort_by
    allowed_sorts = {"soonest_due", "latest_due", "agency_az", "title_az"}
    if sort_by not in allowed_sorts:
        sort_by = "soonest_due"

    # -------- WHERE clause construction --------
    where_clauses = ["1=1"]
    sql_params = {
        "limit_val": page_size,
        "offset_val": offset,
    }

    if agency_filter:
        where_clauses.append("LOWER(agency_name) = LOWER(:agency_name)")
        sql_params["agency_name"] = agency_filter

    if search_filter:
        where_clauses.append("LOWER(title) LIKE :search_value")
        sql_params["search_value"] = f"%{search_filter.lower()}%"

    if due_within is not None:
        # Portable window: [today 00:00, today+due_within+1 00:00)
        start = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=due_within + 1)
        where_clauses.append(
            "due_date IS NOT NULL AND due_date >= :due_start AND due_date < :due_end"
        )
        sql_params["due_start"] = start
        sql_params["due_end"] = end

    # optional status-only filter
    if status_filter == "open":
        where_clauses.append("(opportunities.status IS NULL OR TRIM(LOWER(opportunities.status)) LIKE 'open%')")

    # specialties / tags filter
    tags_raw = query_params.get("tags", "")
    tags_filter = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    if (not tags_filter) and pref_keywords:
        tags_filter = [str(t).strip().lower() for t in pref_keywords if str(t).strip()]
    if tags_filter:
        tag_clauses = []
        for idx, tval in enumerate(tags_filter):
            key = f"tag_{idx}"
            sql_params[key] = f"%{tval}%"
            tag_clauses.append(f"LOWER(COALESCE(ai_tags_json, '')) LIKE :{key}")
        where_clauses.append("(" + " OR ".join(tag_clauses) + ")")

    where_sql = " AND ".join(where_clauses)

    # -------- ORDER BY --------
    if sort_by == "soonest_due":
        order_sql = "(due_date IS NULL) ASC, due_date ASC"
    elif sort_by == "latest_due":
        order_sql = "(due_date IS NULL) ASC, due_date DESC"
    elif sort_by == "agency_az":
        order_sql = "agency_name ASC, title ASC"
    elif sort_by == "title_az":
        order_sql = "title ASC"
    else:
        order_sql = "(due_date IS NULL) ASC, due_date ASC"

    # -------- total count for pagination --------
    async with engine.begin() as conn:
        count_result = await conn.execute(
            text(f"SELECT COUNT(*) FROM opportunities WHERE {where_sql}"),
            sql_params,
        )
        total_count = count_result.scalar() or 0

    total_pages = max(1, math.ceil(total_count / page_size))
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * page_size
        sql_params["offset_val"] = offset

    # -------- pull page rows --------
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"""
                SELECT
                    opportunities.id AS opp_id,
                    opportunities.external_id,
                    opportunities.title,
                    opportunities.agency_name,
                    opportunities.due_date,
                    opportunities.source_url,
                    opportunities.status,
                    COALESCE(opportunities.ai_category, opportunities.category) AS category,
                    opportunities.date_added,
                    (ubt.opportunity_id IS NOT NULL) AS is_tracked
                FROM opportunities
                LEFT JOIN user_bid_trackers ubt
                  ON ubt.opportunity_id = opportunities.id
                 AND ubt.user_id = :track_user_id
                 AND COALESCE(ubt.status, '') NOT LIKE '%archive%'
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT :limit_val OFFSET :offset_val
            """),
            {**sql_params, "track_user_id": user_id},
        )
        rows = result.fetchall()

    # -------- stats card --------
    agencies = []

    async with engine.begin() as conn:
        stats_result = await conn.execute(
            text(f"""
                SELECT
                    COUNT(*) AS result_count,
                    COUNT(DISTINCT agency_name) AS agency_count,
                    MIN(due_date) AS next_due
                FROM opportunities
                WHERE {where_sql}
            """),
            sql_params,
        )
        stats_row = stats_result.first()

        agencies_result = await conn.execute(
            text(
                """
                SELECT DISTINCT agency_name
                FROM opportunities
                WHERE agency_name IS NOT NULL
                  AND TRIM(agency_name) <> ''
                ORDER BY agency_name
                """
            )
        )
        agencies = [row[0] for row in agencies_result.fetchall() if row[0]]

    if not agencies:
        agencies = AGENCIES

    tracking_count = 0
    if user_id:
        async with engine.begin() as conn:
            track_res = await conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM user_bid_trackers
                    WHERE user_id = :uid
                      AND COALESCE(status, '') NOT LIKE '%archive%'
                    """
                ),
                {"uid": user_id},
            )
            tracking_count = track_res.scalar() or 0

    open_count = stats_row[0] if stats_row else 0
    agency_count = stats_row[1] if stats_row else 0
    next_due = stats_row[2] if stats_row and stats_row[2] else None

    if next_due:
        try:
            if hasattr(next_due, "strftime"):
                next_due_str = next_due.strftime("%b %d")
            else:
                next_due_str = str(next_due).split(" ")[0]
        except Exception:
            next_due_str = "-"
    else:
        next_due_str = "-"
    # fallback URLs for agencies whose scraped link is a JS action
    agency_fallback_urls = {
        "Central Ohio Transit Authority (COTA)": "https://cota.dbesystem.com/FrontEnd/proposalsearchpublic.asp",
        "City of Columbus": "https://vendors.columbus.gov/",
        # Track button: use data-* (no inline JS)
    }

    # --- tiny helper for safe HTML attribute values ---
    def _esc_attr(val: str) -> str:
        if val is None:
            return ""
        # minimal but robust escaping for HTML attributes
        return (
            str(val)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _norm_status(val: str) -> str:
        txt = (val or "").strip()
        if "open for bidding" in txt.lower():
            return "Open"
        return txt or "Open"

    # -------- build HTML table rows --------
    table_rows_html = []
    source_icon = """
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
  <polyline points="15 3 21 3 21 9"/>
  <line x1="10" y1="14" x2="21" y2="3"/>
</svg>
""".strip()
    track_icon = """
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
  <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
</svg>
""".strip()

    for opp_id, external_id, title, agency, due, url, status, category, date_added, is_tracked in rows:
        due_date_str = "-"
        due_time_str = ""
        due_cell_class = "due-cell"
        if due:
            try:
                if hasattr(due, "strftime"):
                    d = due
                else:
                    d = dt.datetime.fromisoformat(str(due).split(".")[0].replace("Z", ""))
                due_date_str = d.strftime("%a, %b %d")
                show_time = not (getattr(d, "hour", 0) == 0 and getattr(d, "minute", 0) == 0)
                if show_time:
                    due_time_str = d.strftime("%I:%M %p").lstrip("0")
                today = dt.datetime.utcnow().date()
                days = (d.date() - today).days
                if days <= 7:
                    due_cell_class += " urgent"
            except Exception:
                due_date_str = _esc_attr(str(due))
                due_time_str = ""

        date_added_str = "-"
        if date_added:
            try:
                if hasattr(date_added, "strftime"):
                    date_added_str = date_added.strftime("%b %d")
                else:
                    try:
                        da = dt.datetime.fromisoformat(str(date_added).split(".")[0].replace("Z", ""))
                        date_added_str = da.strftime("%b %d")
                    except Exception:
                        date_added_str = str(date_added).split(" ")[0]
            except Exception:
                date_added_str = "-"
        
        fallback_url = agency_fallback_urls.get(agency or "")

        def is_bad(u: str) -> bool:
            if not u:
                return True
            u = u.strip().lower()
            if "cota.dbesystem.com" in u and "detail" in u:
                return True
            return (u.startswith("javascript:") or u == "#" or u == "about:blank")

        if url and not is_bad(url):
            action_link = f"<a class='action-link' href='{_esc_attr(url)}' target='_blank' title='View source'>{source_icon}</a>"
        elif fallback_url:
            action_link = f"<a class='action-link' href='{_esc_attr(fallback_url)}' target='_blank' title='Open source list'>{source_icon}</a>"
        else:
            action_link = "<span class='action-link' style='opacity:.4;cursor:not-allowed;'>?</span>"

        if external_id:
            solicitation_html = (
                "<button class='rfq-btn solicitation-id' "
                f"data-ext='{_esc_attr(external_id)}' "
                f"data-agency='{_esc_attr(agency or '')}'>"
                f"{_esc_attr(external_id)}</button>"
            )
        else:
            solicitation_html = "<span class='solicitation-id'>-</span>"

        tracked_class = " tracked" if is_tracked else ""
        track_btn_html = (
            f"<button class='track-btn{tracked_class}' "
            f"data-opp-id='{opp_id}' "
            f"data-ext='{_esc_attr(external_id or '')}' "
            f"data-tracked='{1 if is_tracked else 0}' "
            "title='Track this bid'>"
            f"{track_icon}</button>"
        )

        status_txt = _norm_status(status)
        status_class = "open" if status_txt.lower().startswith("open") else "closed"

        row_html = f"""
        <tr class="row-animate" data-opp-id="{opp_id}" data-external-id="{_esc_attr(external_id or '')}" data-agency="{_esc_attr(agency or '')}">
          <td class="col-solicitation">{solicitation_html}</td>
          <td class="col-title">
            <div class="title-cell">
              <a class="title-text" href="/opportunity/{opp_id}">{_esc_attr(title or '')}</a>
              <span class="title-meta">{_esc_attr(category or '')}</span>
            </div>
          </td>
          <td class="col-agency">
            <div class="agency-cell">
              <span class="agency-name">{_esc_attr(agency or '')}</span>
            </div>
          </td>
          <td class="col-added">{date_added_str}</td>
          <td class="col-due">
            <div class="{due_cell_class}">
              <span class="due-date">{due_date_str}</span>
              <span class="due-time">{due_time_str}</span>
            </div>
          </td>
          <td class="col-status">
            <span class="status-badge {status_class}">{_esc_attr(status_txt)}</span>
          </td>
          <td class="col-actions">
            <div class="action-buttons">
              {action_link}
              {track_btn_html}
            </div>
          </td>
        </tr>
        """

        table_rows_html.append(row_html)
# -------- filter form HTML --------
    agency_options_html = [
        f"<option value='' {'selected' if not agency_filter else ''}>All agencies</option>"
    ]
    for ag in agencies:
        sel = "selected" if ag == agency_filter else ""
        safe_ag = _esc_attr(ag)
        agency_options_html.append(f"<option value='{safe_ag}' {sel}>{safe_ag}</option>")

    due_options_display = [
        ("", "Any due date"),
        ("7", "Next 7 days"),
        ("30", "Next 30 days"),
        ("90", "Next 90 days"),
    ]
    duewithin_options_html = []
    for val, label in due_options_display:
        sel = ""
        if (val == "" and due_within is None) or (
            val and due_within is not None and val == str(due_within)
        ):
            sel = "selected"
        duewithin_options_html.append(
            f"<option value='{val}' {sel}>{label}</option>"
        )

    sort_options = [
        ("soonest_due", "Soonest due"),
        ("latest_due", "Latest due"),
        ("agency_az", "Agency A-Z"),
        ("title_az", "Title A-Z"),
    ]
    sort_options_html = []
    for val, label in sort_options:
        sel = "selected" if sort_by == val else ""
        sort_options_html.append(f"<option value='{val}' {sel}>{label}</option>")

    # specialties input & chips
    tags_value = ",".join(tags_filter)

    # -------- pagination links --------
    def page_href(p: int) -> str:
        parts = [f"page={p}"]
        if agency_filter:
            parts.append(f"agency={agency_filter.replace(' ', '+')}")
        if search_filter:
            parts.append(f"search={search_filter.replace(' ', '+')}")
        if tags_filter:
            parts.append(f"tags={'+'.join(tags_filter)}")
        if due_within is not None:
            parts.append(f"due_within={due_within}")
        if sort_by:
            parts.append(f"sort_by={sort_by}")
        if status_filter:
            parts.append(f"status={status_filter}")
        return "/opportunities?" + "&".join(parts)

    window_radius = 2
    start_page = max(1, page - window_radius)
    end_page = min(total_pages, page + window_radius)

    # new pagination buttons (styled)
    pagination_btns = []
    if page > 1:
        pagination_btns.append(f'<button class="page-btn" onclick="window.location=\'{page_href(page-1)}\'">Prev</button>')
    else:
        pagination_btns.append('<button class="page-btn" disabled>Prev</button>')

    for pnum in range(start_page, end_page + 1):
        if pnum == page:
            pagination_btns.append(f'<button class="page-btn active" disabled>{pnum}</button>')
        else:
            pagination_btns.append(f'<button class="page-btn" onclick="window.location=\'{page_href(pnum)}\'">{pnum}</button>')

    if page < total_pages:
        pagination_btns.append(f'<button class="page-btn" onclick="window.location=\'{page_href(page+1)}\'">Next</button>')
    else:
        pagination_btns.append('<button class="page-btn" disabled>Next</button>')

    pagination_html = "<div class='pagination'>" + "".join(pagination_btns) + "</div>"

    stats_html = render_template(
        "stats.html",
        {
            "OPEN_COUNT": str(open_count),
            "AGENCY_COUNT": str(agency_count),
            "NEXT_DUE": _esc_attr(next_due_str),
            "TRACKING_COUNT": str(tracking_count),
        },
    )

    filters_html = render_template(
        "filters.html",
        {
            "AGENCY_OPTIONS": "".join(agency_options_html),
            "SEARCH_VALUE": _esc_attr(search_filter),
            "TAGS_VALUE": _esc_attr(tags_value),
            "DUE_OPTIONS": "".join(duewithin_options_html),
            "STATUS_CHECKED": "checked" if status_filter == "open" else "",
            "SORT_OPTIONS": "".join(sort_options_html),
        },
    )

    showing_start = offset + 1 if rows else 0
    showing_end = offset + len(rows)

    table_html = render_template(
        "table.html",
        {
            "SHOWING_START": str(showing_start),
            "SHOWING_END": str(showing_end),
            "TOTAL_COUNT": str(total_count),
            "ROWS_HTML": "".join(table_rows_html)
            if table_rows_html
            else "<tr><td colspan='7' class='muted'>No results found.</td></tr>",
            "PAGE": str(page),
            "TOTAL_PAGES": str(total_pages),
            "PAGINATION_HTML": pagination_html,
        },
    )

    modal_html = render_template("modal.html")

    body_html = render_template(
        "page.html",
        {
            "STATS_HTML": stats_html,
            "FILTERS_HTML": filters_html,
            "TABLE_HTML": table_html,
            "MODAL_HTML": modal_html,
        },
    )

    return HTMLResponse(
        page_shell(
            body_html,
            title="EasyRFP - Opportunities",
            user_email=user_email,
        )
    )
