        # Track button: use data-* (no inline JS)

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

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities", response_class=HTMLResponse)
async def opportunities(request: Request):
    # -------- auth --------
    user_email = await require_login(request)
    if isinstance(user_email, RedirectResponse):
        return user_email

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
    status_filter = query_params.get("status", "").strip().lower()

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
        where_clauses.append("(status IS NULL OR TRIM(LOWER(status)) LIKE 'open%')")

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
                    id AS opp_id,
                    external_id,
                    title,
                    agency_name,
                    due_date,
                    source_url,
                    status,
                    COALESCE(ai_category, category) AS category,
                    date_added
                FROM opportunities
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT :limit_val OFFSET :offset_val
            """),
            sql_params,
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
    stats_html = f"""
<div class="stats">
  <div class="item">
    <div class="value">{open_count}</div>
    <div class="label">Open bids</div>
  </div>
  <div class="item">
    <div class="value">{agency_count}</div>
    <div class="label">Agencies</div>
  </div>
  <div class="item">
    <div class="value">{next_due_str}</div>
    <div class="label">Next due date</div>
  </div>
</div>
"""

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

    for opp_id, external_id, title, agency, due, url, status, category, date_added in rows:
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

        track_btn_html = (
            "<button class='track-btn' "
            f"data-opp-id='{opp_id}' "
            f"data-ext='{_esc_attr(external_id or '')}' "
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
    chips_html = ""
    if tags_filter:
        chips = "".join([f"<span class='chip'>{_esc_attr(t)}</span>" for t in tags_filter])
        chips_html = f"""
        <div class="filter-chips">
          <span>Specialties:</span>
          {chips}
          <a href="/opportunities?agency=" class="chip-clear">Clear</a>
        </div>
        """

    body_filter_html = f"""
    <section class="card filter-card" style="padding:18px 18px 14px;">
      
      <div class="filter-head">
        <div>
          <h3 class="section-heading">Filters</h3>
          <div class="subtext">Blend your saved specialties with quick tweaks.</div>
        </div>
        <a href="/opportunities?agency=" class="reset-link">Reset</a>
      </div>

      <form method="GET" action="/opportunities">
        <div class="filter-grid">
          <div class="form-col">
            <label class="label-small">Agency</label>
            <select name="agency">
              {''.join(agency_options_html)}
            </select>
          </div>

          <div class="form-col">
            <label class="label-small">Search title</label>
            <input type="text" name="search" value="{search_filter}" placeholder="road, managed services, HVAC..." />
          </div>

          <div class="form-col">
            <label class="label-small">Specialties</label>
            <input type="text" name="tags" value="{tags_value}" placeholder="hvac, paving, it" />
          </div>

          <div class="form-col">
            <label class="label-small">Due within</label>
            <select name="due_within">
              {''.join([f"<option value='{val}' {'selected' if ((val=='' and due_within is None) or (val and due_within is not None and val==str(due_within))) else ''}>{label}</option>" for val,label in [('', 'Any due date'), ('7','Next 7 days'), ('30','Next 30 days'), ('90','Next 90 days')]])}
            </select>
          </div>

          <div class="form-col">
            <label class="label-small">Status</label>
            <label class="checkbox-row"><input type="checkbox" name="status" value="open" {'checked' if status_filter=='open' else ''}/> Open only</label>
          </div>

          <div class="form-col">
            <label class="label-small">Sort by</label>
            <select name="sort_by">
              {''.join([f"<option value='{v}' {'selected' if sort_by==v else ''}>{l}</option>" for v,l in [('soonest_due','Soonest due'),('latest_due','Latest due'),('agency_az','Agency A-Z'),('title_az','Title A-Z')]])}
            </select>
          </div>

          <div class="form-col" style="max-width:220px;">
            <button class="button-primary" type="submit" style="width:100%;">Apply</button>
          </div>
        </div>
      </form>
      {chips_html}
    </section>
    """

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

    # --- redesigned stats + filters + table markup ---
    tracking_count = len(rows)
    stats_html = f"""
    <div class="stats-row fade-in">
      <div class="stat-card">
        <div class="stat-icon open">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="12" y1="18" x2="12" y2="12"/>
            <line x1="9" y1="15" x2="15" y2="15"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{open_count}</span>
          <span class="stat-label">Open Bids</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon agencies">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 21h18"/>
            <path d="M5 21V7l8-4v18"/>
            <path d="M19 21V11l-6-4"/>
            <path d="M9 9v.01"/>
            <path d="M9 12v.01"/>
            <path d="M9 15v.01"/>
            <path d="M9 18v.01"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{agency_count}</span>
          <span class="stat-label">Agencies</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon deadline">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value date">{next_due_str}</span>
          <span class="stat-label">Next Due Date</span>
        </div>
      </div>
      <div class="stat-card featured">
        <div class="stat-icon tracking">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{tracking_count}</span>
          <span class="stat-label">Tracking</span>
        </div>
      </div>
    </div>
    """

    filters_html = f"""
    <div class="filters-card fade-in">
      <div class="filters-header">
        <h3 class="filters-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
          </svg>
          Filters
        </h3>
        <a class="reset-btn" href="/opportunities">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
          </svg>
          Reset
        </a>
      </div>
      <form method="GET" action="/opportunities">
        <div class="filters-grid">
          <div class="filter-group">
            <label class="filter-label">Agency</label>
            <div class="select-wrapper">
              <select class="filter-select" name="agency">{''.join(agency_options_html)}</select>
              <svg class="select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>
          <div class="filter-group">
            <label class="filter-label">Search title</label>
            <div class="search-wrapper">
              <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="m21 21-4.35-4.35"/>
              </svg>
              <input class="filter-input" type="text" name="search" value="{_esc_attr(search_filter)}" placeholder="e.g. HVAC, roofing, IT services..." />
            </div>
          </div>
          <div class="filter-group">
            <label class="filter-label">Specialties</label>
            <div class="select-wrapper">
              <input class="filter-input" type="text" name="tags" value="{_esc_attr(tags_value)}" placeholder="hvac, paving, it" />
            </div>
          </div>
          <div class="filter-group">
            <label class="filter-label">Due within</label>
            <div class="select-wrapper">
              <select class="filter-select" name="due_within">{''.join(duewithin_options_html)}</select>
              <svg class="select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>
        </div>
        <div class="filters-footer">
          <div class="status-toggle">
            <label class="toggle-label">
              <input type="checkbox" name="status" value="open" {'checked' if status_filter=='open' else ''}/>
              <span class="toggle-switch"></span>
              <span class="toggle-text">Open only</span>
            </label>
          </div>
          <div class="sort-group">
            <span class="filter-label">Sort by</span>
            <div class="select-wrapper small">
              <select class="filter-select" name="sort_by">{''.join(sort_options_html)}</select>
              <svg class="select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>
          <button class="apply-btn" type="submit">
            Apply filters
          </button>
        </div>
      </form>
    </div>
    """

    showing_start = offset + 1 if rows else 0
    showing_end = offset + len(rows)

    table_html = f"""
    <div class="table-card fade-in">
      <div class="table-header">
        <div class="results-count">Showing <strong>{showing_start}-{showing_end}</strong> of {total_count} results</div>
        <div class="table-actions">
          <button class="table-action-btn" type="button" onclick="window.location='/opportunities/export'" aria-label="Export results">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14"/><path d="M5 12l7 7 7-7"/><path d="M5 5h14"/>
            </svg>
            Export
          </button>
        </div>
      </div>
      <div class="table-wrapper">
        <table class="opportunities-table">
          <thead>
            <tr>
              <th>Solicitation #</th>
              <th>Title</th>
              <th>Agency</th>
              <th>Date Added</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {''.join(table_rows_html) if table_rows_html else "<tr><td colspan='7' class='muted'>No results found.</td></tr>"}
          </tbody>
        </table>
      </div>
      <div class="table-footer">
        <div class="pagination-info">Page {page} of {total_pages}</div>
        {pagination_html}
      </div>
    </div>
    """

    # -------- modal HTML + JS --------
    # NOTE: this is a plain triple-quoted string, not an f-string,
    # so we can safely use JS template literals (${...}) inside it.
    modal_js = """
<!-- Track Drawer (no uploads here) -->
<div id="bid-drawer" class="drawer hidden">
  <div class="drawer-header">
    <h3 id="drawer-title">Bid Tracker</h3>
    <button class="btn-secondary" style="padding:6px 10px;border-radius:8px;" onclick="closeDrawer()" aria-label="Close">&times;</button>
  </div>
  <div class="drawer-body">
    <section class="card">
      <div class="row" style="justify-content:space-between;align-items:center;gap:10px;">
        <div style="max-width:65%;">
          <div class="label-small">Solicitation</div>
          <div id="drawer-solicitation" style="font-weight:600;word-break:break-word;"></div>
          <input type="hidden" id="opp-id" />
        </div>
        <div style="flex-shrink:0;">
          <a class="btn-secondary" href="/tracker/dashboard" target="_blank">Open My Dashboard &rarr;</a>
        </div>
      </div>
    </section>

    <section class="card">
      <label class="label">Status</label>
      <select id="tracker-status" style="width:100%;">
        <option value="prospecting">Prospecting</option>
        <option value="deciding">Deciding</option>
        <option value="drafting">Drafting</option>
        <option value="submitted">Submitted</option>
        <option value="won">Won</option>
        <option value="lost">Lost</option>
      </select>

      <label class="label" style="margin-top:10px;">Notes</label>
      <textarea id="tracker-notes" rows="4" placeholder="Add notes."></textarea>

      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn" id="save-tracker-btn">Save</button>
        <button class="btn-secondary" onclick="window.open('/tracker/dashboard?focus='+document.getElementById('opp-id').value,'_blank')">
          Manage Files in Dashboard
        </button>
      </div>
      <div id="tracker-save-msg" class="muted" style="margin-top:8px;"></div>
    </section>
  </div>
</div>
<!-- Modal overlay for RFQ / solicitation detail -->
<div id="rfq-modal-overlay" style="display:none;">
  <div id="rfq-modal-card">
    <button onclick="closeDetailModal()" id="rfq-close">&times;</button>
    <div id="rfq-modal-content">Loading.</div>
  </div>
</div>

<script>
async function api(path, init = {}) {
  const token = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||[])[1] || "";
  const method = (init.method||"GET").toUpperCase();
  const headers = Object.assign({}, init.headers||{});
  if (method !== "GET") { headers["X-CSRF-Token"] = token; }
  const res = await fetch(path, { credentials: "include", ...init, headers });
  if (res.status === 401) {
    const next = location.pathname + location.search;
    const oppId = document.getElementById("opp-id")?.value || "";
    const hash = oppId ? ("#openTracker:" + oppId) : "";
    window.location.href = "/login?next=" + encodeURIComponent(next + hash);
    throw new Error("Auth required");
  }
  return res;
}

async function openTrackerDrawer(oppId, extId) {
  document.getElementById('opp-id').value = oppId;
  document.getElementById('drawer-solicitation').textContent = extId || '(no ext id)';
  document.getElementById('tracker-save-msg').textContent = '';

  try {
    await api(`/tracker/${oppId}/track`, { method: 'POST' });
    const res = await api(`/tracker/${oppId}`);
    if (res.ok) {
      const t = await res.json();
      document.getElementById('tracker-status').value = t.status || 'prospecting';
      document.getElementById('tracker-notes').value  = t.notes  || '';
    }
  } catch (_) { return; }

  document.getElementById('bid-drawer').classList.remove('hidden');
}

document.addEventListener('click', async (e) => {
  const rfq = e.target.closest('.rfq-btn');
  if (rfq) {
    e.preventDefault();
    const id = rfq.getAttribute('data-ext') || '';
    const ag = rfq.getAttribute('data-agency') || '';
    if (typeof openDetailModal === 'function') {
      openDetailModal(id, ag);
    }
    return;
  }
  const track = e.target.closest('.track-btn');
  if (track) {
    openTrackerDrawer(track.dataset.oppId, track.dataset.ext || '');
    return;
  }
  if (e.target && e.target.id === 'save-tracker-btn') {
    const oppId = document.getElementById('opp-id').value;
    const payload = {
      status: document.getElementById('tracker-status').value,
      notes:  document.getElementById('tracker-notes').value
    };
    try {
      const res = await api(`/tracker/${oppId}`, {
        method: 'PATCH',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      document.getElementById('tracker-save-msg').textContent =
        res.ok ? 'Saved.' : 'Save failed.';
    } catch (_) {}
  }
});
</script>

"""

    body_html = f"""
<main class="page">
  <div class="page-header fade-in">
    <div class="page-title-section">
      <h1 class="page-title">Open Opportunities</h1>
      <p class="page-subtitle">Live feed from municipal procurement portals. Updated automatically every few hours.</p>
    </div>
  </div>
  {stats_html}
  {filters_html}
  {table_html}
</main>

<!-- vendor sidebar markup -->
<div id="vendor-overlay" onclick="closeVendorGuide()"></div>
<div id="vendor-guide-panel">
  <div id="vendor-guide-header">
    <div>
      <h2>How to bid</h2>
      <div id="vendor-guide-agency" style="font-size:12px;color:#64748b;">City of Columbus</div>
    </div>
    <button onclick="closeVendorGuide()" style="border:0;background:#e2e8f0;width:28px;height:28px;border-radius:999px;font-size:16px;cursor:pointer;">&times;</button>
  </div>
  <div id="vendor-guide-content">Loading...</div>
</div>

{modal_js}
<link rel="stylesheet" href="/static/css/vendor.css"> 
<link rel="stylesheet" href="/static/css/highlight.css"> 
<link rel="stylesheet" href="/static/css/bid_tracker.css"> 
<link rel="stylesheet" href="/static/css/opportunities.css?v=2"> 

<script src="/static/js/vendor.js"></script>
<script src="/static/js/highlight.js"></script>
<script src="/static/js/rfq_modal.js"></script>
<script src="/static/js/bid_tracker.js"></script>

"""

    return HTMLResponse(
        page_shell(
            body_html,
            title="EasyRFP - Opportunities",
            user_email=user_email,
        )
    )
