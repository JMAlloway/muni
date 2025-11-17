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
        return HTMLResponse(page_shell(body, title="Muni Alerts - My Bids", user_email=None), status_code=200)

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
                "<option value='{val}'>[{ext}] {title} â€” {agency}</option>"
                .format(
                    val=str(it["opportunity_id"]),
                    ext=esc_text((it.get("external_id") or "â€”")),
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

    <!-- Upload Manager removed -->\n  <div class="toolbar" id="dashboard-actions" style="margin-top:16px;">
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
      </select>\n      <input id="search-filter" placeholder="Search title, ID, agency" style="min-width:220px; padding:8px 10px; border:1px solid #e5e7eb; border-radius:10px;" />\n      <button id="reset-filters" class="btn-secondary" type="button">Reset</button>\n    </div>\n    <div class="muted" id="summary-count" style="font-size:12px; margin-left:auto;"></div>\n  </div>

  <!-- Provide items directly to the grid as a data attribute for tracker_dashboard.js -->
  <div id="tracked-grid" class="tracked-grid" data-items='__ITEMS_JSON_ESC__'></div>
</section>

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

<link rel="stylesheet" href="/static/dashboard.css?v=5">
<link rel="stylesheet" href="/static/bid_tracker.css">



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
<script src="/static/vendor.js?v=4"></script>
<script src="/static/tracker_dashboard.js?v=14"></script>
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
        .replace("__ITEMS_JSON_ESC__", items_json_escaped)
    )
    return HTMLResponse(page_shell(body, title="Muni Alerts My Bids", user_email=user_email))














