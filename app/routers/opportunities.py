# app/routers/opportunities.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
import math
import json

from app.db_core import engine
from app.routers._layout import page_shell
from app.auth_utils import require_login

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

    # fallback to saved preference if no agency specified in URL
    if not agency_param_present and not agency_filter:
        async with engine.begin() as conn:
            pref_res = await conn.execute(
                text("SELECT agencies FROM user_preferences WHERE user_email = :email"),
                {"email": user_email},
            )
            pref_row = pref_res.first()
        if pref_row and pref_row[0]:
            try:
                saved_agencies = json.loads(pref_row[0])
                if isinstance(saved_agencies, list) and saved_agencies:
                    agency_filter = saved_agencies[0]
            except Exception:
                pass

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
        where_clauses.append("agency_name = :agency_name")
        sql_params["agency_name"] = agency_filter

    if search_filter:
        where_clauses.append("LOWER(title) LIKE :search_value")
        sql_params["search_value"] = f"%{search_filter.lower()}%"

    if due_within is not None:
        # NOTE for SQLite. For Postgres you'd rewrite this.
        due_modifier = f"+{due_within} days"
        where_clauses.append(
            "due_date IS NOT NULL "
            "AND DATE(due_date) >= DATE('now') "
            "AND DATE(due_date) <= DATE('now', :due_modifier)"
        )
        sql_params["due_modifier"] = due_modifier

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
                    external_id,      -- RFQ / Solicitation #
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
    async with engine.begin() as conn:
        stats_result = await conn.execute(
            text(f"""
                SELECT
                    COUNT(*) AS open_count,
                    COUNT(DISTINCT agency_name) AS agency_count,
                    MIN(due_date) AS next_due
                FROM opportunities
                WHERE status = 'open' AND {where_sql}
            """),
            sql_params,
        )
        stats_row = stats_result.first()

    open_count = stats_row[0] if stats_row else 0
    agency_count = stats_row[1] if stats_row else 0
    next_due = stats_row[2] if stats_row and stats_row[2] else None

    if next_due:
        try:
            if hasattr(next_due, "strftime"):
                next_due_str = next_due.strftime("%Y-%m-%d")
            else:
                next_due_str = str(next_due).split(" ")[0]
        except Exception:
            next_due_str = "—"
    else:
        next_due_str = "—"

    stats_html = f"""
<div style="
    display:flex;
    flex-wrap:wrap;
    gap:24px;
    align-items:flex-start;
    background:#f9fafb;
    border:1px solid #e5e7eb;
    border-radius:12px;
    padding:12px 16px;
    margin:12px 0 20px;
">
    <div style="flex:0 0 auto;">
        <div style="font-size:18px;font-weight:600;color:#111;">{open_count}</div>
        <div class="muted" style="font-size:12px;line-height:16px;">Open bids</div>
    </div>
    <div style="flex:0 0 auto;">
        <div style="font-size:18px;font-weight:600;color:#111;">{agency_count}</div>
        <div class="muted" style="font-size:12px;line-height:16px;">Municipalities</div>
    </div>
    <div style="flex:0 0 auto;">
        <div style="font-size:18px;font-weight:600;color:#111;">{next_due_str}</div>
        <div class="muted" style="font-size:12px;line-height:16px;">Next due date</div>
    </div>
</div>
"""
    # fallback URLs for agencies whose scraped link is a JS action
    agency_fallback_urls = {
        "Central Ohio Transit Authority (COTA)": "https://cota.dbesystem.com/FrontEnd/proposalsearchpublic.asp",
        "City of Columbus": "https://vendors.columbus.gov/",
        # add more as you run into them...
    }

        # -------- build HTML table rows --------
    table_rows_html = []

    for external_id, title, agency, due, url, status, category, date_added in rows:
        # format due date like "10/27/2025 08:00 AM"
        if due:
            try:
                if hasattr(due, "strftime"):
                    due_str = due.strftime("%m/%d/%Y %I:%M %p")
                else:
                    due_str = str(due)
            except Exception:
                due_str = "TBD"
        else:
            due_str = "TBD"

        # clickable solicitation # -> opens modal, and now we pass agency
        if external_id:
            safe_agency_attr = agency.replace('"', "&quot;") if agency else ""
            rfq_html = (
                "<button "
                f"onclick=\"openDetailModal('{external_id}', '{safe_agency_attr}')\" "
                "style=\"all:unset; cursor:pointer; color:var(--accent-text); "
                "text-decoration:underline; font-weight:500;\">"
                f"{external_id} &#8595;</button>"
            )
        else:
            rfq_html = "—"

        # pill/badge for status
        badge_html = f"<span class='pill'>{status or 'open'}</span>"

                # NEW: source link column content (with agency fallback)
        fallback_url = agency_fallback_urls.get(agency or "")

        def is_bad(u: str) -> bool:
            if not u:
                return True
            u = u.strip().lower()
            # COTA detail pages require a session cookie — they won't open directly
            if "cota.dbesystem.com" in u and "detail" in u:
                return True
            return (
                u.startswith("javascript:")
                or u == "#"
                or u == "about:blank"
                or "rid=unknown" in u
            )


        if url and not is_bad(url):
            # good, real URL from the ingestor
            link_html = (
                f"<a href='{url}' target='_blank' "
                "style='color:var(--accent-text);text-decoration:underline;'>Open</a>"
            )
        elif fallback_url:
            # bad/missing link → fall back to the agency's main bid list
            if "cota" in (agency or "").lower() and external_id:
                label = f"Open list (find {external_id})"
            else:
                label = "Open list"
            link_html = (
                f"<a href='{fallback_url}' target='_blank' "
                f"style='color:var(--accent-text);text-decoration:underline;'>{label}</a>"
            )

        else:
            # nothing we can do
            link_html = "<span class='muted'>—</span>"

         # ✅ ADD THIS RIGHT HERE
        # format date_added like "11/02/2025"
        if date_added:
            try:
                if hasattr(date_added, "strftime"):
                    date_added_str = date_added.strftime("%m/%d/%Y")
                else:
                    date_added_str = str(date_added).split(" ")[0]
            except Exception:
                date_added_str = "—"
        else:
            date_added_str = "—"

        # NEW: vendor guide link (for now, only Columbus)
        if agency == "City of Columbus":
            vendor_html = (
                "<button "
                "onclick=\"openVendorGuide('city-of-columbus')\" "
                "style=\"all:unset; cursor:pointer; color:var(--accent-text); text-decoration:underline;\">"
                "How to bid"
                "</button>"
            )
        else:
            vendor_html = ""

        # build the row AFTER we've defined everything
        row_html = (
            f"<tr data-external-id='{external_id or ''}' data-agency='{agency or ''}'>"
            # 1) Solicitation #
            f"<td style='vertical-align:top;font-size:14px;font-weight:500;color:#111827;'>{rfq_html}</td>"
            # 2) Title
            f"<td style='vertical-align:top;font-size:14px;color:#111827;'>{title}</td>"
            # 3) Agency
            f"<td style='vertical-align:top;font-size:13px;color:#4b5563;'>{agency or ''}</td>"
            # 4) Date Added  ✅
            f"<td style='vertical-align:top;font-size:13px;color:#4b5563;'>{date_added_str}</td>"
            # 5) Due Date
            f"<td style='vertical-align:top;font-size:13px;color:#111827;'>{due_str}</td>"
            # 6) Type
            f"<td style='vertical-align:top;font-size:13px;color:#4b5563;'>{category or ''}</td>"
            # 7) Status
            f"<td style='vertical-align:top;'>{badge_html}</td>"
            # 8) Source Link
            f"<td style='vertical-align:top;font-size:13px;'>{link_html}</td>"
            # 9) Vendor Guide link (new)
            f"<td style='vertical-align:top;font-size:13px;'>{vendor_html}</td>"
            "</tr>"
        )

        table_rows_html.append(row_html)


    # -------- filter form HTML --------
    agencies = [
        "City of Columbus",
        "City of Gahanna",
        "City of Grove City",
        "City of Marysville",
        "City of Whitehall",
        "City of Grandview Heights",
        "City of Worthington",
        "Delaware County",
        "Solid Waste Authority of Central Ohio (SWACO)",
        "Central Ohio Transit Authority (COTA)",
        "Franklin County, Ohio",
        "City of Westerville",
        "Columbus Metropolitan Library",
        "Columbus Metropolitan Housing Authority",
        "Columbus and Franklin County Metro Parks",
        "Columbus Regional Airport Authority (CRAA)",
        "Mid-Ohio Regional Planning Commission (MORPC)",
        "Dublin City Schools",
        "Village of Minerva Park",
        "City of New Albany",
        "Ohio Buys",
    ]

    agency_options_html = [
        f"<option value='' {'selected' if not agency_filter else ''}>All agencies</option>"
    ]
    for ag in agencies:
        sel = "selected" if ag == agency_filter else ""
        agency_options_html.append(f"<option value='{ag}' {sel}>{ag}</option>")

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
        ("agency_az", "Agency A–Z"),
        ("title_az", "Title A–Z"),
    ]
    sort_options_html = []
    for val, label in sort_options:
        sel = "selected" if sort_by == val else ""
        sort_options_html.append(f"<option value='{val}' {sel}>{label}</option>")

    body_filter_html = f"""
    <form method="GET" action="/opportunities" style="margin-bottom:16px;">
        <div class="form-row">
            <div class="form-col">
                <label class="label-small">Agency</label>
                <select name="agency">
                    {''.join(agency_options_html)}
                </select>
            </div>

            <div class="form-col">
                <label class="label-small">Search title</label>
                <input
                    type="text"
                    name="search"
                    value="{search_filter}"
                    placeholder="road, IT managed services..."
                />
            </div>

            <div class="form-col">
                <label class="label-small">Due within</label>
                <select name="due_within">
                    {''.join(duewithin_options_html)}
                </select>
            </div>

            <div class="form-col">
                <label class="label-small">Sort by</label>
                <select name="sort_by">
                    {''.join(sort_options_html)}
                </select>
            </div>

            <div class="form-col" style="align-self:flex-end;">
                <button class="button-primary" type="submit">Filter →</button>
                <div style="margin-top:8px;">
                    <a href="/opportunities?agency="
                       style="font-size:12px;color:var(--accent-text);text-decoration:underline;">
                        Reset / Show all bids
                    </a>
                </div>
            </div>
        </div>
    </form>
    """

    # -------- pagination links --------
    def page_href(p: int) -> str:
        parts = [f"page={p}"]
        if agency_filter:
            parts.append(f"agency={agency_filter.replace(' ', '+')}")
        if search_filter:
            parts.append(f"search={search_filter.replace(' ', '+')}")
        if due_within is not None:
            parts.append(f"due_within={due_within}")
        if sort_by:
            parts.append(f"sort_by={sort_by}")
        return "/opportunities?" + "&".join(parts)

    window_radius = 2
    start_page = max(1, page - window_radius)
    end_page = min(total_pages, page + window_radius)

    page_links_html_parts = []

    # prev
    if page > 1:
        page_links_html_parts.append(
            f"<a class='page-link' href='{page_href(page-1)}'>&larr; Prev</a>"
        )
    else:
        page_links_html_parts.append(
            "<span class='page-link disabled'>&larr; Prev</span>"
        )

    # page nums
    for p in range(start_page, end_page + 1):
        if p == page:
            page_links_html_parts.append(
                f"<span class='page-link current'>{p}</span>"
            )
        else:
            page_links_html_parts.append(
                f"<a class='page-link' href='{page_href(p)}'>{p}</a>"
            )

    # next
    if page < total_pages:
        page_links_html_parts.append(
            f"<a class='page-link' href='{page_href(page+1)}'>Next &rarr;</a>"
        )
    else:
        page_links_html_parts.append(
            "<span class='page-link disabled'>Next &rarr;</span>"
        )

    pagination_bar_html = (
        "<div class='pagination-bar'>"
        + "".join(page_links_html_parts)
        + f"<span class='muted' style='margin-left:auto;'>"
        f"Page {page} of {total_pages} &middot; {total_count} total"
        f"</span>"
        + "</div>"
    )
    # -------- modal HTML + JS --------
    # NOTE: this is a plain triple-quoted string, not an f-string,
    # so we can safely use JS template literals (${...}) inside it.
    modal_js = """
    <!-- Modal overlay for RFQ / solicitation detail -->
    <div id="rfq-modal-overlay" style="
        display:none;
        position:fixed;
        left:0;
        top:0;
        width:100vw;
        height:100vh;
        background:rgba(0,0,0,0.4);
        z-index:1000;
        align-items:flex-start;
        justify-content:center;
        overflow-y:auto;
        padding:40px 16px;
    ">
        <div id="rfq-modal-card" style="
            background:#fff;
            border-radius:12px;
            box-shadow:0 20px 40px rgba(0,0,0,0.2);
            max-width:800px;
            width:100%;
            padding:24px;
            position:relative;
            font-family:system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        ">
            <button onclick="closeDetailModal()" style="
                position:absolute;
                top:12px;
                right:12px;
                border:0;
                background:#eee;
                border-radius:6px;
                font-size:14px;
                line-height:1;
                padding:4px 8px;
                cursor:pointer;
            ">✕</button>
            <div id="rfq-modal-content" style="font-size:14px; color:#111;">
                Loading...
            </div>
        </div>
    </div>

    <script>
    async function openDetailModal(rfqId, agencyName) {
        const overlay = document.getElementById("rfq-modal-overlay");
        const content = document.getElementById("rfq-modal-content");

        overlay.style.display = "flex";
        content.innerHTML = "<div style='font-size:14px;color:#555;'>Loading...</div>";

        let endpoint = "";
        if (agencyName && agencyName.toLowerCase().includes("cota")) {
            endpoint = "/cota_detail/" + encodeURIComponent(rfqId);
        } else if (agencyName && agencyName.toLowerCase().includes("columbus")) {
            endpoint = "/columbus_detail/" + encodeURIComponent(rfqId);
        } else if (agencyName && agencyName.toLowerCase().includes("gahanna")) {
            endpoint = "/gahanna_detail/" + encodeURIComponent(rfqId);
        } else {
            endpoint = "/columbus_detail/" + encodeURIComponent(rfqId);
        }

        try {
            const resp = await fetch(endpoint);
            if (!resp.ok) {
                content.innerHTML = "<div style='color:#b91c1c;'>Unable to load details.</div>";
                return;
            }
            const data = await resp.json();
            const safe = (v) => (v ? String(v) : "");

            if (data.error) {
                content.innerHTML = `
                    <div style="color:#b91c1c;font-weight:600;margin-bottom:.5rem;">
                        Unable to load full opportunity details.
                    </div>
                    <div style="font-size:.8rem;color:#666;white-space:pre-wrap;
                                max-height:200px;overflow-y:auto;border:1px solid #eee;
                                padding:.5rem;border-radius:4px;background:#fafafa;">
                        ${safe(data.error)}
                        ${safe(data.status_code ? "Status " + data.status_code : "")}
                        ${safe(data.text || "")}
                    </div>
                `;
                return;
            }
            // You can render more details here if needed
        } catch (err) {
            content.innerHTML = "<div style='color:#b91c1c;'>Error loading details.</div>";
        }
    }

    function closeDetailModal() {
        const overlay = document.getElementById("rfq-modal-overlay");
        overlay.style.display = "none";
    }
    </script>
    """

    highlight_js = """
    <style>
    .highlight-opportunity {
        animation: pulse-highlight 1.3s ease-out 1;
        outline: 2px solid #f97316;
        outline-offset: 2px;
        background: rgba(249, 115, 22, 0.08);
    }
    @keyframes pulse-highlight {
        0%   { background: rgba(249, 115, 22, 0.25); }
        50%  { background: rgba(249, 115, 22, 0.10); }
        100% { background: transparent; }
    }
    </style>

    <script>
    document.addEventListener("DOMContentLoaded", function () {
        const params = new URLSearchParams(window.location.search);
        const ext = params.get("ext");
        const agency = params.get("agency") || "";
        const id = params.get("id");

        const lookup = ext || id;
        if (!lookup) return;

        const selector =
            "[data-external-id='" + lookup + "'], " +
            "[data-id='" + lookup + "'], " +
            "[data-opportunity='" + lookup + "']";

        const row = document.querySelector(selector);

        if (row) {
            row.scrollIntoView({ behavior: "smooth", block: "center" });
            row.classList.add("highlight-opportunity");
            setTimeout(() => {
                row.classList.remove("highlight-opportunity");
            }, 1600);
        }

        if (typeof openDetailModal === "function") {
            openDetailModal(lookup, agency);
        }
    });
    </script>
    """

    # -------- final page HTML --------
    body_html = f"""
    <div style="display:flex; gap:18px; align-items:flex-start;">
        <!-- LEFT: main content -->
        <div style="flex:1 1 auto; min-width:0;">
            <section class="card">
                <h2 class="section-heading">Open Opportunities</h2>
                <p class="subtext">
                    Live feed from municipal procurement portals. Sorted by soonest due date.
                    Updated automatically every few hours.
                </p>

                {stats_html}
                {body_filter_html}

                <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th style="min-width:140px;">Solicitation #</th>
                            <th style="min-width:280px;">Title</th>
                            <th style="min-width:160px;">Agency</th>
                            <th style="min-width:140px;">Date Added</th>
                            <th style="min-width:140px;">Due Date</th>
                            <th style="min-width:140px;">Type</th>
                            <th style="min-width:80px;">Status</th>
                            <th style="min-width:120px;">Source Link</th>
                            <th style="min-width:120px;">How to Bid</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(table_rows_html) if table_rows_html else "<tr><td colspan='9' class='muted'>No results found.</td></tr>"}
                    </tbody>
                </table>
                </div>

                {pagination_bar_html}
            </section>

            <section class="card">
                <div class="mini-head">Coverage (pilot)</div>
                <div class="mini-desc">
                    City of Columbus, COTA, Gahanna, Grove City, and Delaware County sources are live.
                    You can filter, sort, and target deadlines.
                </div>
            </section>
        </div>
    </div>

    <!-- vendor sidebar markup -->
    <div id="vendor-overlay" onclick="closeVendorGuide()"></div>
    <div id="vendor-guide-panel">
      <div id="vendor-guide-header">
        <div>
          <h2>How to bid</h2>
          <div id="vendor-guide-agency" style="font-size:12px;color:#64748b;">City of Columbus</div>
        </div>
        <button onclick="closeVendorGuide()" style="border:0;background:#e2e8f0;width:28px;height:28px;border-radius:999px;font-size:16px;cursor:pointer;">×</button>
      </div>
      <div id="vendor-guide-content">Loading…</div>
    </div>

    {modal_js}
    {highlight_js}
    <link rel="stylesheet" href="/static/vendor.css">
    <script src="/static/vendor.js"></script>
    """

    return HTMLResponse(
        page_shell(
            body_html,
            title="Muni Alerts – Opportunities",
            user_email=user_email,
        )
    )
