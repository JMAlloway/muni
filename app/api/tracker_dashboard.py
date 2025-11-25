from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.core.db_core import engine
from app.api._layout import page_shell
from app.auth.session import get_current_user_email
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
          <p class="subtext">You're not signed in. Please log in to see your dashboard.</p>
          <a class="button-primary" href="/login?next=/tracker/dashboard">Sign in</a>
        </section>
        """
        return HTMLResponse(page_shell(body, title="EasyRFP - My Bids", user_email=None), status_code=200)

    # --- fetch tracked items for this user (and their team, if applicable) ---
    team_name = None
    team_owner_email = None
    team_member_count = 0
    user_id = None
    team_id = None

    async with engine.begin() as conn:
        user_res = await conn.exec_driver_sql(
            "SELECT id, team_id FROM users WHERE lower(email) = lower(:email) LIMIT 1",
            {"email": user_email},
        )
        user_row = user_res.first()
        if user_row:
            user_id = user_row._mapping.get("id")
            team_id = user_row._mapping.get("team_id")

        if team_id:
            meta_res = await conn.exec_driver_sql(
                """
                SELECT t.name, owner.email AS owner_email
                FROM teams t
                LEFT JOIN users owner ON owner.id = t.owner_user_id
                WHERE t.id = :team
                LIMIT 1
                """,
                {"team": team_id},
            )
            meta_row = meta_res.first()
            if meta_row:
                meta_map = meta_row._mapping
                team_name = meta_map.get("name") or "Team"
                team_owner_email = meta_map.get("owner_email")
            count_res = await conn.exec_driver_sql(
                "SELECT COUNT(*) FROM team_members WHERE team_id = :team AND (accepted_at IS NOT NULL OR role = 'owner')",
                {"team": team_id},
            )
            team_member_count = count_res.scalar() or 0

        params = {"email": user_email, "user_id": user_id, "team_id": team_id}
        filter_clause = "tracker_user.team_id = :team_id" if team_id else "tracker_user.id = :user_id"

        sql = f"""
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
          COALESCE(u.file_count, 0) AS file_count,
          tracker_user.email AS tracked_by,
          CASE WHEN lower(tracker_user.email) = lower(:email) THEN 1 ELSE 0 END AS is_mine
        FROM user_bid_trackers t
        JOIN opportunities o ON o.id = t.opportunity_id
        JOIN users tracker_user ON tracker_user.id = t.user_id
        LEFT JOIN u ON u.user_id = t.user_id AND u.opportunity_id = t.opportunity_id
        WHERE {filter_clause}
        ORDER BY (o.due_date IS NULL) ASC, o.due_date ASC, t.created_at DESC
        """
        rows = await conn.exec_driver_sql(sql, params)
        items = [dict(r._mapping) for r in rows.fetchall()]

    for it in items:
        it["is_mine"] = bool(it.get("is_mine"))

    # --- dynamic bits (built separately; no f-strings in HTML) ---
    def esc_text(x: str) -> str:
        return html.escape(x or "")

    options_html = "".join(
        "<option value='{val}'>[{ext}] {title} - {agency}</option>".format(
            val=str(it["opportunity_id"]),
            ext=esc_text(it.get("external_id") or "-"),
            title=esc_text(it.get("title", "")),
            agency=esc_text(it.get("agency_name", "")),
        )
        for it in items
    )

    total_items = len(items)
    def _is_due_soon(d):
        if not d:
            return False
        try:
            import datetime as _dt
            return (_dt.datetime.fromisoformat(str(d)) - _dt.datetime.utcnow()).days <= 7
        except Exception:
            return False
    due_soon_count = sum(1 for it in items if _is_due_soon(it.get("due_date")))
    won_count = sum(1 for it in items if str(it.get("status", "")).lower() == "won")

    team_bar_html = ""
    if team_id:
        member_label = f"{team_member_count} member{'s' if team_member_count != 1 else ''}"
        team_bar_html = f"""
<div class="team-bar fade-in">
  <div class="team-info">
    <div class="team-avatars">
      <div class="team-avatar">JD</div>
      <div class="team-avatar" style="background: linear-gradient(135deg, #3b82f6, #60a5fa);">SK</div>
      <div class="team-avatar" style="background: linear-gradient(135deg, #8b5cf6, #a78bfa);">MR</div>
      <div class="team-avatar add">+</div>
    </div>
    <div class="team-details">
      <span class="team-label">Your Team</span>
      <span><strong>{esc_text(team_name or 'Team')}</strong> • {esc_text(member_label)}</span>
    </div>
  </div>
  <button class="shared-dashboard-btn" type="button">Team Dashboard</button>
</div>
"""

    # JSON for the page (embedded in a JSON script tag)
    items_json = json.dumps(items)
    items_json_escaped = (
        items_json
        .replace("</", "<\/")  # prevent </script> early close
    )

    # --- plain triple-quoted HTML with placeholders ---
    body = """
__TEAM_BAR__

<div class="stats-grid">
  <div class="stat-card featured fade-in stagger-1">
    <div class="stat-icon">📈</div>
    <div class="stat-label">Active Bids</div>
    <div class="stat-value">{total_items}</div>
    <span class="stat-change positive">↑ {total_items} this week</span>
  </div>
  <div class="stat-card fade-in stagger-2">
    <div class="stat-icon">⏰</div>
    <div class="stat-label">Due This Week</div>
    <div class="stat-value">{due_soon_count}</div>
    <span class="stat-change negative">↓ {due_soon_count} urgent</span>
  </div>
  <div class="stat-card fade-in stagger-3">
    <div class="stat-icon">✅</div>
    <div class="stat-label">Won This Quarter</div>
    <div class="stat-value">{won_count}</div>
    <span class="stat-change positive">↑ 23% vs Q3</span>
  </div>
  <div class="stat-card fade-in stagger-4">
    <div class="stat-icon">💰</div>
    <div class="stat-label">Pipeline Value</div>
    <div class="stat-value">$2.4M</div>
    <span class="stat-change positive">↑ $340K added</span>
  </div>
</div>

<div class="grid-3">
  <div>
    <div class="timeline-section fade-in stagger-2">
      <div class="timeline-header">
        <div>
          <h3 class="section-title">Upcoming Deadlines</h3>
          <p class="section-subtitle">Next 7 days</p>
        </div>
        <div class="section-tabs">
          <button class="section-tab active">Week</button>
          <button class="section-tab">Month</button>
          <button class="section-tab">All</button>
        </div>
      </div>
      <div class="timeline">
        <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-content"><div class="timeline-date">Today, 2:00 PM</div><div class="timeline-title">Safety Boots Supply Contract</div><div class="timeline-desc">City of Columbus • Final submission deadline</div></div></div>
        <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-content"><div class="timeline-date">Tomorrow, 1:30 PM</div><div class="timeline-title">Yard Waste Processing RFP</div><div class="timeline-desc">Franklin County • Proposal due</div></div></div>
        <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-content"><div class="timeline-date">Nov 25, 1:00 PM</div><div class="timeline-title">HVAC Services Contract</div><div class="timeline-desc">COTA • Technical documents due</div></div></div>
        <div class="timeline-item upcoming"><div class="timeline-dot"></div><div class="timeline-content"><div class="timeline-date">Nov 28, 3:00 PM</div><div class="timeline-title">IT Support Services</div><div class="timeline-desc">Ohio DOT • Pre-qualification deadline</div></div></div>
      </div>
    </div>

    <div class="section-header fade-in stagger-3">
      <div>
        <h2 class="section-title">Tracked Solicitations</h2>
        <p class="section-subtitle">{total_items} active opportunities</p>
      </div>
      <div class="section-tabs">
        <button class="section-tab active" type="button">All</button>
        <button class="section-tab" type="button">Due Soon</button>
        <button class="section-tab" type="button">Won</button>
      </div>
    </div>

    <div class="toolbar fade-in stagger-3" id="dashboard-actions" style="margin-top:8px;">
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
          <option value="soonest">Due Date ↑</option>
          <option value="latest">Due Date ↓</option>
          <option value="agency">Agency A-Z</option>
          <option value="title">Title A-Z</option>
        </select>
        <input id="search-filter" type="search" placeholder="Search title, ID, agency" />
        <button id="reset-filters" class="btn-secondary" type="button">Reset</button>
      </div>
      <div class="result-count" id="summary-count"></div>
    </div>

    <div id="tracked-grid" class="tracked-grid solicitations-list" data-items='__ITEMS_JSON_ESC__' data-user-email="__USER_EMAIL__" data-user-id="__USER_ID__"></div>
  </div>

  <div>
    <div class="chart-card fade-in stagger-3" style="margin-bottom: 24px;">
      <div class="chart-header">
        <h3 class="chart-title">Bid Status Overview</h3>
      </div>
      <div class="donut-chart">
        <svg viewBox="0 0 200 200">
          <circle class="donut-segment" cx="100" cy="100" r="70" stroke="#126a45" stroke-dasharray="175 440" stroke-dashoffset="0"/>
          <circle class="donut-segment" cx="100" cy="100" r="70" stroke="#22c55e" stroke-dasharray="110 440" stroke-dashoffset="-175"/>
          <circle class="donut-segment" cx="100" cy="100" r="70" stroke="#f59e0b" stroke-dasharray="88 440" stroke-dashoffset="-285"/>
          <circle class="donut-segment" cx="100" cy="100" r="70" stroke="#3b82f6" stroke-dasharray="67 440" stroke-dashoffset="-373"/>
        </svg>
        <div class="donut-center">
          <div class="donut-value">{total_items}</div>
          <div class="donut-label">Total Bids</div>
        </div>
      </div>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-dot" style="background: #126a45;"></span>Active (4)</div>
        <div class="legend-item"><span class="legend-dot" style="background: #22c55e;"></span>Won (3)</div>
        <div class="legend-item"><span class="legend-dot" style="background: #f59e0b;"></span>Pending (2)</div>
        <div class="legend-item"><span class="legend-dot" style="background: #3b82f6;"></span>Review (3)</div>
      </div>
    </div>

    <div class="activity-feed fade-in stagger-4">
      <div class="activity-header"><h3 class="activity-title">Recent Activity</h3></div>
      <div class="activity-item"><div class="activity-icon">📄</div><div class="activity-content"><div class="activity-text"><strong>Sarah K.</strong> uploaded pricing sheet for HVAC contract</div><div class="activity-time">2 hours ago</div></div></div>
      <div class="activity-item"><div class="activity-icon">✅</div><div class="activity-content"><div class="activity-text"><strong>Mike R.</strong> completed site visit for Yard Waste RFP</div><div class="activity-time">Yesterday at 3:45 PM</div></div></div>
      <div class="activity-item"><div class="activity-icon">🏆</div><div class="activity-content"><div class="activity-text">Contract <strong>awarded</strong> for Fleet Maintenance Services</div><div class="activity-time">2 days ago</div></div></div>
      <div class="activity-item"><div class="activity-icon">➕</div><div class="activity-content"><div class="activity-text"><strong>You</strong> added 2 new opportunities to tracking</div><div class="activity-time">3 days ago</div></div></div>
    </div>
  </div>
</div>

<!-- Team thread sidebar -->
<div id="thread-overlay"></div>
<aside id="thread-drawer" aria-hidden="true">
  <header>
    <div>
      <div id="thread-label" class="muted" style="font-size:12px;">Team room thread</div>
      <h3 id="thread-title" style="margin:2px 0 4px 0;">Thread</h3>
      <div id="thread-subtitle" class="muted" style="font-size:12px;"></div>
    </div>
    <button class="icon-btn" id="close-thread" type="button">x</button>
  </header>
  <div class="thread-body">
    <div id="thread-messages" class="thread-messages">
      <div class="muted">Select a solicitation to see its thread.</div>
    </div>
  </div>
  <div class="thread-compose">
    <textarea id="thread-input" placeholder="@alex can you send pricing?"></textarea>
    <div class="thread-actions">
      <button id="thread-send" class="btn" type="button">Send</button>
      <button id="thread-cancel" class="btn-secondary" type="button">Close</button>
    </div>
  </div>
</aside>

<!-- Overlay + drawer used by vendor.js -->
<div id="guide-overlay"></div>
<aside id="guide-drawer" aria-hidden="true">
  <header>
    <div>
      <h3 id="guide-title">How to bid</h3>
      <div id="guide-agency" class="muted"></div>
    </div>
    <button class="icon-btn" onclick="TrackerGuide.close()">Ã—</button>
  </header>
  <div id="guide-content" class="guide-content">Loading…</div>
</aside>

<link rel="stylesheet" href="/static/css/dashboard.css?v=8">
<link rel="stylesheet" href="/static/css/bid_tracker.css">



<!-- Upload Sidebar (drawer) -->
<div id="upload-overlay" style="display:none; position:fixed; inset:0; background:rgba(2,6,23,.4);"></div>
<aside id="upload-drawer" aria-hidden="true" style="position:fixed; top:0; right:-520px; width:520px; height:100%; background:#fff; border-left:1px solid #e5e7eb; box-shadow:-6px 0 20px rgba(2,6,23,.08); display:flex; flex-direction:column; transition:right .25s ease; z-index:1001;">
  <header style="display:flex; align-items:center; justify-content:space-between; padding:14px; border-bottom:1px solid #eef2f7;">
    <div>
      <h3 style="margin:0; font-size:16px;">Upload Files</h3>
      <div id="upload-agency" class="muted" style="font-size:12px;"></div>
    </div>
    <button class="icon-btn" id="close-upload-d" type="button">×</button>
  </header>
  <div style="padding:14px; display:grid; gap:10px; overflow:auto;">
    <div>
      <label class="label-small">Choose solicitation</label>
      <select id="upload-target-d" style="width:100%;">
        <option value="">Select</option>
        __ITEM_OPTIONS__
      </select>
    </div>
    <div id="dz-d" class="dz" style="background:#f8fafc;border:2px dashed #d1d5db;border-radius:12px;padding:18px;text-align:center;user-select:none;">
      <div class="dz-inner" style="display:grid;gap:6px;justify-items:center;">
        <div class="dz-icon" style="font-size:28px;opacity:.7;">📎</div>
        <div class="dz-title" style="font-weight:600;">Drag & drop files here</div>
        <div class="dz-sub" style="font-size:12px;color:#6b7280">or</div>
        <button type="button" id="pick-d" class="btn">Choose Files</button>
        <input type="file" id="picker-d" multiple hidden />
      </div>
    </div>
    <div>
      <div class="muted" style="font-size:12px; margin-bottom:6px;">To upload (<span id="queue-count">0</span>)</div>
      <ul id="queue-d" class="file-list" style="list-style:none;margin:0 0 8px 0;padding:0;"></ul>
      <div style="display:flex; gap:8px; align-items:center;">
        <button id="do-upload-d" class="btn" disabled>Upload All</button>
        <button id="clear-queue-d" class="btn-secondary" type="button">Clear</button>
      </div>
    </div>
    <div class="row" style="display:flex; align-items:center; justify-content:space-between;">
      <h4 style="margin:0;">My Files</h4>
      <button id="download-zip-d" class="btn-secondary" disabled>Download ZIP</button>
    </div>
    <ul id="files-d" class="file-list" style="list-style:none;margin:0;padding:0;"></ul>
  </div>
</aside>

<script>
(function(){\n  var CSRF=(document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||[])[1]||"";
  var overlay = document.getElementById('upload-overlay');
  var drawer  = document.getElementById('upload-drawer');
  var closeBtn = document.getElementById('close-upload-d');
  var dz = document.getElementById('dz-d');
  var pickBtn = document.getElementById('pick-d');
  var picker = document.getElementById('picker-d');
  var uploadBtn = document.getElementById('do-upload-d');
  var clearBtn = document.getElementById('clear-queue-d');
  var queueList = document.getElementById('queue-d');
  var queueCount = document.getElementById('queue-count');
  var fileList = document.getElementById('files-d');
  var targetSel = document.getElementById('upload-target-d');
  var zipBtn = document.getElementById('download-zip-d');

  var queued = [];
  function esc(s){ s=String(s==null?"":s); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function open(){ overlay.style.display='block'; drawer.setAttribute('aria-hidden','false'); drawer.style.right='0'; }
  function close(){ overlay.style.display='none'; drawer.setAttribute('aria-hidden','true'); drawer.style.right='-520px'; queued=[]; renderQueue(); }
  overlay.addEventListener('click', close);
  if (closeBtn) closeBtn.addEventListener('click', close);

  function renderList(items){
    if(!items||!items.length){ fileList.innerHTML = "<li class='muted'>No files yet.</li>"; zipBtn.disabled=true; return; }
    zipBtn.disabled=false; fileList.innerHTML='';
    for(var i=0;i<items.length;i++){
      var f=items[i]; var li=document.createElement('li'); li.style.display='flex'; li.style.justifyContent='space-between'; li.style.alignItems='center'; li.style.gap='8px'; li.style.padding='6px 0';
      var name=document.createElement('span'); name.innerHTML = esc(f.filename);
      var meta=document.createElement('span'); meta.className='muted'; var kb=Math.round(((f.size||0)/1024)); meta.textContent=' ('+kb+' KB)';
      var left=document.createElement('span'); left.appendChild(name); left.appendChild(meta);
      var actions=document.createElement('span'); actions.style.display='flex'; actions.style.gap='8px'; actions.style.alignItems='center';
      var a=document.createElement('a'); a.className='btn-link'; a.target='_blank'; a.href=f.download_url; a.textContent='Download';
      var rn=document.createElement('button'); rn.type='button'; rn.className='btn-secondary'; rn.setAttribute('data-action','rename'); rn.setAttribute('data-id', String(f.id)); rn.textContent='Rename';
      var del=document.createElement('button'); del.type='button'; del.className='icon-btn'; del.setAttribute('title','Delete'); del.setAttribute('data-action','delete'); del.setAttribute('data-id', String(f.id)); del.textContent='×';
      actions.appendChild(a); actions.appendChild(rn); actions.appendChild(del);
      li.appendChild(left); li.appendChild(actions); fileList.appendChild(li);
    }
  }

  async function loadFiles(){ var oid=targetSel.value; if(!oid){ renderList([]); return; }
    try{ var res=await fetch('/uploads/list/'+oid, { credentials:'include' }); if(res.ok){ var data=await res.json(); renderList(data);} else { renderList([]);} } catch(e){ renderList([]);} }

  dz.addEventListener('dragover', function(e){ e.preventDefault(); e.stopPropagation(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', function(e){ e.stopPropagation(); dz.classList.remove('dragover'); });
  dz.addEventListener('drop', function(e){ e.preventDefault(); e.stopPropagation(); dz.classList.remove('dragover'); var files=e.dataTransfer.files; for(var i=0;i<files.length;i++) queued.push(files[i]); renderQueue(); });
  drawer.addEventListener('dragover', function(e){ e.preventDefault(); e.stopPropagation(); });
  drawer.addEventListener('drop', function(e){ e.preventDefault(); e.stopPropagation(); var files=(e.dataTransfer&&e.dataTransfer.files)||[]; for(var i=0;i<files.length;i++) queued.push(files[i]); renderQueue(); });
  overlay.addEventListener('dragover', function(e){ e.preventDefault(); });
  overlay.addEventListener('drop', function(e){ e.preventDefault(); var files=(e.dataTransfer&&e.dataTransfer.files)||[]; for(var i=0;i<files.length;i++) queued.push(files[i]); renderQueue(); });

  pickBtn.addEventListener('click', function(){ picker.click(); });
  picker.addEventListener('change', function(){ var files=picker.files; for(var i=0;i<files.length;i++) queued.push(files[i]); renderQueue(); });

  function renderQueue(){ queueList.innerHTML=''; if(!queued.length){ queueCount.textContent='0'; uploadBtn.disabled=true; return; } queueCount.textContent=String(queued.length); uploadBtn.disabled=false; for(var i=0;i<queued.length;i++){ var li=document.createElement('li'); li.style.display='flex'; li.style.justifyContent='space-between'; li.style.alignItems='center'; li.style.gap='8px'; li.style.padding='4px 0'; var left=document.createElement('span'); left.textContent=queued[i].name; var right=document.createElement('span'); right.className='muted'; right.textContent=Math.round((queued[i].size||0)/1024)+' KB'; var btn=document.createElement('button'); btn.type='button'; btn.setAttribute('data-remove-idx', String(i)); btn.textContent='×'; btn.className='icon-btn'; btn.title='Remove'; var wrap=document.createElement('span'); wrap.style.display='flex'; wrap.style.alignItems='center'; wrap.style.gap='6px'; wrap.appendChild(right); wrap.appendChild(btn); li.appendChild(left); li.appendChild(wrap); queueList.appendChild(li);} }
  clearBtn.addEventListener('click', function(){ queued=[]; picker.value=''; renderQueue(); });
  queueList.addEventListener('click', function(e){ var b=e.target.closest('[data-remove-idx]'); if(!b) return; var idx=parseInt(b.getAttribute('data-remove-idx')); if(!isNaN(idx)){ queued.splice(idx,1); renderQueue(); } });
  uploadBtn.addEventListener('click', async function(){ var oid=targetSel.value; if(!oid||!queued.length){ return; } var fd=new FormData(); fd.append('opportunity_id', oid); for(var i=0;i<queued.length;i++) fd.append('files', queued[i], queued[i].name); var res=await fetch('/uploads/add',{method:'POST', body:fd, credentials:'include', headers:{'X-CSRF-Token': CSRF}}); if(res.ok){ queued=[]; picker.value=''; renderQueue(); await loadFiles(); }});
  targetSel.addEventListener('change', loadFiles);
  fileList.addEventListener('click', async function(e){ var b=e.target.closest('[data-action]'); if(!b) return; var id=b.getAttribute('data-id'); if(!id) return; if(b.getAttribute('data-action')==='delete'){ try{ await fetch('/uploads/'+id, { method:'DELETE', credentials:'include', headers:{'X-CSRF-Token': CSRF} }); }catch(_){} await loadFiles(); return; } if(b.getAttribute('data-action')==='rename'){ var current=(b.closest('li').querySelector('span')||{}).textContent||''; var nn=prompt('Rename file', current); if(nn && nn.trim()){ try{ await fetch('/uploads/'+id, { method:'PATCH', headers:{'Content-Type':'application/json'}, credentials:'include', body: JSON.stringify({ filename: nn.trim() }) }); }catch(_){} await loadFiles(); } return; } });

  window.openUploadDrawer = async function(obj){ var oid=(obj && obj.opportunity_id) ? obj.opportunity_id : obj; try{ await fetch('/tracker/'+oid+'/track',{method:'POST', credentials:'include', headers:{'X-CSRF-Token': CSRF}});}catch(_){} targetSel.value=String(oid||''); var agencyEl=document.getElementById('upload-agency'); if(agencyEl && obj && obj.agency_name) agencyEl.textContent=obj.agency_name; open(); loadFiles(); };

  // Do not auto-open the upload drawer on page load.
})();
</script>
<script src="/static/js/vendor.js?v=4"></script>
<script src="/static/js/tracker_dashboard.js?v=22"></script>
<script>
// Inline: live search + summary layered on top of card rendering
(function(){\n  var CSRF=(document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||[])[1]||"";
  var input = document.getElementById('search-filter');
  var summary = document.getElementById('summary-count');
  var resetBtn = document.getElementById('reset-filters');
  function update(){
    var q = (input && input.value || '').trim().toLowerCase();
    var cards = Array.prototype.slice.call(document.querySelectorAll('.tracked-card'));
    var shown = 0;
    for (var i=0;i<cards.length;i++){
      var card = cards[i];
      var ok = !q || (card.textContent||'').toLowerCase().indexOf(q) >= 0;
      card.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }
    if (window.updateDashboardSummary) {
      window.updateDashboardSummary();
    } else if (summary){ summary.textContent = shown + '/' + cards.length + ' shown'; }
  }
  if (input){ input.addEventListener('input', update); }
  if (resetBtn){ resetBtn.addEventListener('click', function(){ if (input) input.value=''; update(); }); }
  window.addEventListener('load', function(){ setTimeout(update, 300); });
})();
</script>
"""

    # inject dynamic strings safely
    body = (
        body
        .replace("__ITEM_OPTIONS__", options_html)
        .replace("__TEAM_BAR__", team_bar_html or "")
        .replace("__ITEMS_JSON_ESC__", items_json_escaped)
        .replace("__USER_EMAIL__", esc_text(user_email or ""))
        .replace("__USER_ID__", esc_text(str(user_id or "")))
    )
    return HTMLResponse(page_shell(body, title="EasyRFP My Bids", user_email=user_email))














