from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.db_core import engine
from app.routers._layout import page_shell
from app.session import get_current_user_email
import json
import html

router = APIRouter(tags=["tracker"])


@router.get("/tracker/dashboard", response_class=HTMLResponse)
async def tracker_dashboard(request: Request):
    # --- auth via session cookie ---
    user_email = get_current_user_email(request)
    if not user_email:
        body = """
        <section class="card">
          <h2 class="section-heading">Sign in required</h2>
          <p class="subtext">You’re not signed in. Please log in to see your dashboard.</p>
          <a class="button-primary" href="/login?next=/tracker/dashboard">Sign in →</a>
        </section>
        """
        return HTMLResponse(page_shell(body, title="Muni Alerts – My Bids", user_email=None), status_code=200)

    # --- fetch tracked items for this user ---
    sql = """
    WITH u AS (
      SELECT user_id, opportunity_id, COUNT(*) AS file_count, MAX(created_at) AS last_upload_at
      FROM user_uploads
      GROUP BY user_id, opportunity_id
    )
    SELECT
      t.opportunity_id,
      o.external_id,
      o.title,
      o.agency_name,
      o.due_date,
      COALESCE(o.ai_category, o.category) AS category,
      o.source_url,
      t.status,
      t.notes,
      t.created_at AS tracked_at,
      COALESCE(u.file_count, 0) AS file_count
    FROM user_bid_trackers t
    JOIN opportunities o ON o.id = t.opportunity_id
    LEFT JOIN u ON u.user_id = t.user_id AND u.opportunity_id = t.opportunity_id
    WHERE t.user_id = (SELECT id FROM users WHERE email = :email LIMIT 1)
    ORDER BY (o.due_date IS NULL) ASC, o.due_date ASC, t.created_at DESC
    """
    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql(sql, {"email": user_email})
        items = [dict(r._mapping) for r in rows.fetchall()]

    # --- dynamic bits (built separately; no f-strings in HTML) ---
    def esc_text(x: str) -> str:
        return html.escape(x or "")

    options_html = "".join(
        [
            (
                "<option value='{val}'>[{ext}] {title} — {agency}</option>"
                .format(
                    val=str(it["opportunity_id"]),
                    ext=esc_text((it.get("external_id") or "—")),
                    title=esc_text(it.get("title", "")),
                    agency=esc_text(it.get("agency_name", ""))
                )
            )
            for it in items
        ]
    )

    # JSON for the page (embedded in a JSON script tag)
    items_json = json.dumps(items)
    items_json_escaped = (
        items_json
        .replace("</", "<\\/")  # prevent </script> early close
    )

    # --- plain triple-quoted HTML with placeholders ---
    body = """
<section class="card">
  <div class="head-row">
    <h2 class="section-heading">My Tracked Solicitations</h2>
    <div class="muted">Status, files, and step-by-step guidance.</div>
  </div>

  <!-- Upload Manager -->
  <div class="card" style="margin-top:4px;">
    <label class="label">Upload files to a tracked solicitation</label>
    <div class="form-row" style="gap:10px; align-items:flex-end;">
      <div style="flex:1 1 360px;">
        <label class="label-small">Choose solicitation</label>
        <select id="upload-target" style="width:100%;">
          <option value="">— Select —</option>
          __ITEM_OPTIONS__
        </select>
      </div>
      <div>
        <button id="refresh-files" class="btn-secondary">Refresh files</button>
      </div>
    </div>

    <!-- Drag & Drop -->
    <div id="dz" class="dz" style="margin-top:10px;">
      <div class="dz-inner">
        <div class="dz-icon">⬆︎</div>
        <div class="dz-title">Drag & drop files here</div>
        <div class="dz-sub">or</div>
        <button type="button" id="pick" class="btn">Choose Files</button>
        <input type="file" id="picker" multiple hidden />
      </div>
    </div>

    <div style="margin-top:10px;">
      <button id="do-upload" class="btn">Upload</button>
    </div>

    <div class="row" style="margin-top:14px; justify-content:space-between;">
      <h4 style="margin:0;">My Files</h4>
      <button id="download-zip" class="btn-secondary" disabled>Download ZIP</button>
    </div>
    <ul id="files" class="file-list"></ul>
  </div>

  <div class="toolbar" id="dashboard-actions" style="margin-top:16px;">
    <div class="filters">
      <select id="status-filter">
        <option value="">All statuses</option>
        <option value="prospecting">Prospecting</option>
        <option value="deciding">Deciding</option>
        <option value="drafting">Drafting</option>
        <option value="submitted">Submitted</option>
        <option value="won">Won</option>
        <option value="lost">Lost</option>
      </select>
      <select id="agency-filter">
        <option value="">All agencies</option>
        <option value="City of Columbus">City of Columbus</option>
        <option value="Central Ohio Transit Authority (COTA)">COTA</option>
      </select>
      <select id="sort-by">
        <option value="soonest">Soonest due</option>
        <option value="latest">Latest due</option>
        <option value="agency">Agency A–Z</option>
        <option value="title">Title A–Z</option>
      </select>
    </div>
  </div>

  <!-- Safer JSON embed -->
  <div id="tracked-grid" class="tracked-grid"></div>
  <script id="tracked-items" type="application/json">__ITEMS_JSON_ESC__</script>
</section>

<!-- Overlay + drawer used by vendor.js -->
<div id="guide-overlay"></div>
<aside id="guide-drawer" aria-hidden="true">
  <header>
    <div>
      <h3 id="guide-title">How to bid</h3>
      <div id="guide-agency" class="muted"></div>
    </div>
    <button class="icon-btn" onclick="TrackerGuide.close()">×</button>
  </header>
  <div id="guide-content" class="guide-content">Loading…</div>
</aside>

<link rel="stylesheet" href="/static/dashboard.css">
<link rel="stylesheet" href="/static/bid_tracker.css">

<script src="/static/vendor.js"></script>
<script>
/* ===== Simple upload JS (dashboard only) – no template literals ===== */
(function(){
  var dz = document.getElementById('dz');
  var pickBtn = document.getElementById('pick');
  var picker = document.getElementById('picker');
  var uploadBtn = document.getElementById('do-upload');
  var fileList = document.getElementById('files');
  var targetSel = document.getElementById('upload-target');
  var refreshBtn = document.getElementById('refresh-files');
  var zipBtn = document.getElementById('download-zip');

  var queued = [];

  function esc(s) {
    s = String(s == null ? "" : s);
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function renderList(items) {
    if (!items || !items.length) {
      fileList.innerHTML = "<li class='muted'>No files yet.</li>";
      zipBtn.disabled = true;
      return;
    }
    zipBtn.disabled = false;
    // Build DOM safely (no backticks)
    fileList.innerHTML = "";
    for (var i=0; i<items.length; i++) {
      var f = items[i];
      var li = document.createElement('li');

      var s1 = document.createElement('span');
      s1.innerHTML = esc(f.filename);

      var s2 = document.createElement('span');
      s2.className = "muted";
      var kb = Math.round(((f.size||0)/1024));
      s2.textContent = " (" + kb + " KB)";

      var a = document.createElement('a');
      a.className = "btn-link";
      a.target = "_blank";
      a.href = f.download_url;
      a.textContent = "Download";

      li.appendChild(s1);
      li.appendChild(s2);
      li.appendChild(a);
      fileList.appendChild(li);
    }
  }

  async function loadFiles() {
    var oid = targetSel.value;
    if (!oid) { renderList([]); return; }
    try {
      var res = await fetch('/uploads/list/' + oid);
      if (res.ok) {
        var data = await res.json();
        renderList(data);
      } else {
        renderList([]);
      }
    } catch (e) { renderList([]); }
  }

  dz.addEventListener('dragover', function(e){ e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', function(){ dz.classList.remove('dragover'); });
  dz.addEventListener('drop', function(e){
    e.preventDefault();
    dz.classList.remove('dragover');
    var files = e.dataTransfer.files;
    for (var i=0; i<files.length; i++) queued.push(files[i]);
  });

  pickBtn.addEventListener('click', function(){ picker.click(); });
  picker.addEventListener('change', function(){
    var files = picker.files;
    for (var i=0; i<files.length; i++) queued.push(files[i]);
  });

  uploadBtn.addEventListener('click', async function(){
    var oid = targetSel.value;
    if (!oid || !queued.length) return;
    var fd = new FormData();
    fd.append('opportunity_id', oid);
    for (var i=0; i<queued.length; i++) fd.append('files', queued[i], queued[i].name);
    var res = await fetch('/uploads/add', { method:'POST', body: fd });
    if (res.ok) { queued = []; picker.value = ''; await loadFiles(); }
  });

  refreshBtn.addEventListener('click', loadFiles);
  targetSel.addEventListener('change', loadFiles);

  // Provide items to your grid renderer from the JSON blob
  try {
    var blob = document.getElementById('tracked-items');
    var items = JSON.parse(blob.textContent || "[]");

    // If your /static/tracker_dashboard.js expects data-items on #tracked-grid,
    // set it programmatically now (avoids HTML-attribute escaping headaches).
    var grid = document.getElementById('tracked-grid');
    grid.setAttribute('data-items', JSON.stringify(items));

    // optional: focus via ?focus=ID
    var params = new URLSearchParams(location.search);
    var focus = params.get('focus');
    if (focus) {
      var opts = targetSel.options;
      for (var j=0; j<opts.length; j++) {
        if (opts[j].value === focus) { targetSel.value = focus; break; }
      }
      loadFiles();
    }
  } catch (e) {
    console.warn("Failed to parse tracked items JSON:", e);
  }
})();
</script>

<script src="/static/tracker_dashboard.js"></script>
"""

    # inject dynamic strings safely
    body = (
        body
        .replace("__ITEM_OPTIONS__", options_html)
        .replace("__ITEMS_JSON_ESC__", items_json_escaped)
    )
    return HTMLResponse(page_shell(body, title="Muni Alerts – My Bids", user_email=user_email))
