(function () {
  function getCSRF(){ try { return (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||[])[1] || null; } catch(_) { return null; } }

  const grid = document.getElementById("tracked-grid");
  let items = JSON.parse(grid.getAttribute("data-items") || "[]");
  const currentUserEmail = (grid.getAttribute("data-user-email") || "").toLowerCase();
  const currentUserId = parseInt(grid.getAttribute("data-user-id") || "", 10) || null;

  const selStatus = document.getElementById("status-filter");
  const selAgency = document.getElementById("agency-filter");
  const selSort   = document.getElementById("sort-by");
  const ORDER_KEY = 'dashboard_order_v1';
  function loadOrder(){
    try { return JSON.parse(localStorage.getItem(ORDER_KEY)||'[]'); } catch(_) { return []; }
  }
  function saveOrder(list){
    try { localStorage.setItem(ORDER_KEY, JSON.stringify(list||[])); } catch(_) {}
    try {
      fetch('/dashboard/order', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': (getCSRF()||'') },
        body: JSON.stringify({ order: list||[] })
      }).catch(()=>{});
    } catch(_) {}
  }
  async function syncOrderFromServer(){
    try {
      const res = await fetch('/dashboard/order', { credentials: 'include' });
      if (!res.ok) return;
      const data = await res.json();
      if (data && Array.isArray(data.order)) {
        try { localStorage.setItem(ORDER_KEY, JSON.stringify(data.order)); } catch(_) {}
      }
    } catch(_) {}
  }
  function applyManualOrder(arr){
    const order = loadOrder();
    if (!order || !order.length) return arr;
    const idx = new Map(order.map((id,i)=>[String(id), i]));
    arr.sort((a,b)=> (idx.get(String(a.opportunity_id)) ?? 1e9) - (idx.get(String(b.opportunity_id)) ?? 1e9));
    return arr;
  }
  const txtSearch = document.getElementById("search-filter");
  const btnReset  = document.getElementById("reset-filters");
  const summaryEl = document.getElementById("summary-count");
  const threadUI = {
    overlay: document.getElementById("thread-overlay"),
    drawer: document.getElementById("thread-drawer"),
    title: document.getElementById("thread-title"),
    subtitle: document.getElementById("thread-subtitle"),
    list: document.getElementById("thread-messages"),
    input: document.getElementById("thread-input"),
    send: document.getElementById("thread-send"),
    cancel: document.getElementById("thread-cancel"),
    label: document.getElementById("thread-label")
  };
  const threadState = { oid: null, meta: null };

  function pct(n){ return Math.max(0, Math.min(100, Math.round(n))); }
  function computeProgress(it){
    let p = 0;
    if (["deciding","drafting","submitted","won","lost"].includes((it.status||"").toLowerCase())) p += 25;
    if ((it.file_count||0) > 0) p += 25;
    if (it.due_date) p += 25;
    if ((it.notes||"").trim().length > 0) p += 25;
    return p;
  }
  function dueStr(d){ if (!d) return "TBD"; return String(d).replace("T"," ").slice(0,16); }
  function statusBadge(s){ return `<span class="status-badge">${(s||"prospecting")}</span>`; }

  // --- server-backed collaboration ------------------------------------------
  const collabState = {
    notesCache: {}, // oid -> notes array
    open: {}, // oid -> bool
    fetching: new Set(),
  };
  function setAssignee(){ /* server-backed assignee not yet wired */ }
  function collabFor(){ return {}; }
  async function fetchNotes(oid){
    if (!oid || collabState.fetching.has(oid)) return;
    collabState.fetching.add(oid);
    try {
      const res = await fetch(`/api/team/notes?opportunity_id=${encodeURIComponent(oid)}`, { credentials:'include' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      collabState.notesCache[oid] = (data.notes || []).map(n => Object.assign({}, n, { body: noteBody(n) }));
      if (threadState.oid === oid) renderThread();
    } catch(_) {} finally {
      collabState.fetching.delete(oid);
    }
  }
  async function ensureNotes(oid){
    if (!oid) return;
    if (collabState.notesCache[oid]) return;
    await fetchNotes(oid);
  }
  async function postNote(oid, body){
    const text = (body || "").trim();
    if (!text) return;
    const res = await fetch('/api/team/notes', {
      method:'POST',
      credentials:'include',
      headers:{ 'Content-Type':'application/json', 'X-CSRF-Token': (getCSRF()||'') },
      body: JSON.stringify({ opportunity_id: oid, body: text })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await fetchNotes(oid);
  }
  function getNotes(oid){ return collabState.notesCache[oid] || []; }
  function toggleCollab(oid, force){
    collabState.open[oid] = force !== undefined ? !!force : !collabState.open[oid];
  }
  function fmtDateShort(iso){
    try { return new Date(iso).toLocaleString(undefined,{month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"}); } catch(_) { return ""; }
  }
  function escHtml(str){
    return (str||"").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c] || c));
  }
  function highlightMentions(str){
    return escHtml(str).replace(/@([a-zA-Z0-9._-]+)/g, '<span class="mention">@$1</span>');
  }
  function noteBody(n){
    if (!n) return "";
    return (n.body || n.text || "").toString();
  }

  // Inject minimal styles for collab UI
  (function(){
    const css = `
      .collab-box { margin-top:12px; padding:12px; border:1px solid #e5e7eb; border-radius:12px; background:#f8fafc; }
      .collab-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
      .collab-head .label { font-size:12px; font-weight:700; color:#0f172a; }
      .collab-head .chip { font-size:11px; padding:4px 8px; border-radius:999px; background:#e0e7ff; color:#4338ca; }
      .collab-toggle { border:none; background:none; color:#6b7280; cursor:pointer; font-size:14px; display:flex; align-items:center; gap:6px; }
      .collab-toggle:hover { color:#111827; }
      .collab-toggle .arrow { transition: transform .15s ease; display:inline-block; }
      .collab-box.collapsed .collab-body { display:none; }
      .collab-box.collapsed .collab-toggle .arrow { transform: rotate(-90deg); }
      .collab-row { display:flex; gap:8px; align-items:center; margin-bottom:8px; }
      .collab-row input { flex:1; border:1px solid #d1d5db; border-radius:10px; padding:8px 10px; }
      .collab-notes { display:grid; gap:8px; margin-bottom:10px; }
      .collab-note { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:8px 10px; font-size:13px; color:#111827; box-shadow:0 2px 6px rgba(0,0,0,0.04); }
      .collab-note .meta { font-size:11px; color:#6b7280; margin-top:4px; }
      .mention { color:#4338ca; font-weight:700; }
      .collab-form { display:grid; gap:6px; }
      .collab-form textarea { width:100%; min-height:60px; padding:8px 10px; border:1px solid #d1d5db; border-radius:10px; resize:vertical; }
      .collab-actions { display:flex; gap:8px; align-items:center; }
    `;
    const el = document.createElement('style');
    el.textContent = css;
    document.head.appendChild(el);
  })();

  function threadMetaFromItem(it){
    if (!it) return null;
    return {
      opportunity_id: it.opportunity_id,
      title: it.title || "Team thread",
      agency_name: it.agency_name || "",
      external_id: it.external_id || ""
    };
  }
  function setThreadMeta(meta){
    threadState.meta = meta;
    threadState.oid = meta ? meta.opportunity_id : null;
    if (threadUI.title) threadUI.title.textContent = meta ? (meta.title || "Team thread") : "Team thread";
    if (threadUI.subtitle) {
      const bits = [];
      if (meta && meta.agency_name) bits.push(meta.agency_name);
      if (meta && meta.external_id) bits.push(meta.external_id);
      threadUI.subtitle.textContent = bits.join(" - ");
    }
  }
  function renderThread(){
    if (!threadUI.list) return;
    const oid = threadState.oid;
    const notes = oid ? getNotes(oid) : [];
    if (!oid) {
      threadUI.list.innerHTML = "<div class='muted'>Select a solicitation to see its thread.</div>";
      return;
    }
    if (!notes.length) {
      threadUI.list.innerHTML = "<div class='muted'>No messages yet. Start the thread with an @mention.</div>";
      return;
    }
    threadUI.list.innerHTML = notes.map(n=>{
      const text = highlightMentions(noteBody(n));
      const ts = fmtDateShort(n.created_at || n.id);
      const author = n.author_email || "Someone";
      const isMineEmail = currentUserEmail && author && author.toLowerCase() === currentUserEmail;
      const isMineId = currentUserId && n.author_user_id && String(n.author_user_id) === String(currentUserId);
      const isMine = !!(isMineEmail || isMineId);
      const label = isMine ? "You" : author;
      return `<div class="thread-message ${isMine ? 'mine' : ''}">
        <div>${text}</div>
        <div class="meta"><span class="author">${escHtml(label)}</span>${ts ? `<span>&#183;</span><span>${ts}</span>` : ''}</div>
      </div>`;
    }).join("");
  }
  function openThread(meta){
    if (!meta || !meta.opportunity_id) return;
    setThreadMeta(meta);
    if (threadUI.overlay) {
      threadUI.overlay.style.display = 'block';
      threadUI.overlay.setAttribute('aria-hidden','false');
    }
    if (threadUI.drawer) threadUI.drawer.setAttribute('aria-hidden','false');
    fetchNotes(meta.opportunity_id).then(()=>{ renderThread(); render(); }).catch(()=>{ renderThread(); });
    if (threadUI.input) threadUI.input.focus();
  }
  function closeThread(){
    threadState.oid = null;
    threadState.meta = null;
    if (threadUI.overlay) {
      threadUI.overlay.style.display = 'none';
      threadUI.overlay.setAttribute('aria-hidden','true');
    }
    if (threadUI.drawer) threadUI.drawer.setAttribute('aria-hidden','true');
    if (threadUI.list) threadUI.list.innerHTML = "<div class='muted'>Select a solicitation to see its thread.</div>";
  }
  async function sendThreadMessage(){
    const oid = threadState.oid;
    if (!oid || !threadUI.input) return;
    const text = (threadUI.input.value || "").trim();
    if (!text) return;
    if (threadUI.send) threadUI.send.disabled = true;
    try {
      await postNote(oid, text);
      threadUI.input.value = "";
      await fetchNotes(oid);
      render();
      renderThread();
    } catch(_) {} finally {
      if (threadUI.send) threadUI.send.disabled = false;
    }
  }
  if (threadUI.overlay) threadUI.overlay.addEventListener('click', closeThread);
  if (threadUI.cancel) threadUI.cancel.addEventListener('click', closeThread);
  if (threadUI.send) threadUI.send.addEventListener('click', sendThreadMessage);
  if (threadUI.input) threadUI.input.addEventListener('keydown', function(e){
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault();
      sendThreadMessage();
    }
  });
  const closeThreadBtn = document.getElementById("close-thread");
  if (closeThreadBtn) closeThreadBtn.addEventListener('click', closeThread);

  function openUploads(it){
    if (window.openUploadDrawer) return window.openUploadDrawer(it);
    // legacy fallback if drawer not present (kept for safety)
    const labels = Array.from(document.querySelectorAll('.label'));
    const lbl = labels.find(el => /Upload files to a tracked solicitation/i.test(el.textContent||''));
    const card = lbl ? lbl.closest('.card') : null;
    const sel = document.getElementById('upload-target');
    if (card && sel) {
      card.style.display = '';
      const oid = String(it.opportunity_id || '');
      sel.value = oid;
      try { sel.dispatchEvent(new Event('change', { bubbles: true })); } catch(_) {}
      const dz = document.getElementById('dz');
      if (dz && dz.scrollIntoView) dz.scrollIntoView({ behavior:'smooth', block:'start' });
      return;
    }
    if (window.trackAndOpenUploads) return window.trackAndOpenUploads(it.opportunity_id);
    alert("Upload manager not available.");
  }

  // 🔗 Use your existing vendor guide loader
  function mapAgencyToSlug(name){
    const n = (name||"").toLowerCase();
    if (n.includes("city of columbus")) return "city-of-columbus";
    if (n.includes("central ohio transit authority") || n.includes("cota")) return "central-ohio-transit-authority";
    if (n.includes("swaco")) return "swaco";
    if (n.includes("airport") || n.includes("craa") || n.includes("columbus regional airport authority")) return "craa";
    if (n.includes("gahanna")) return "gahanna";
    if (n.includes("delaware county")) return "delaware-county";
    // add more as you create them
    return null;
  }

  function openGuide(it){
    const slug = mapAgencyToSlug(it.agency_name);
    if (slug && window.openVendorGuide) {
      // Pass context; your vendor.js can optionally use it
      window.openVendorGuide(slug, {
        external_id: it.external_id,
        title: it.title,
        due_date: it.due_date,
        agency_name: it.agency_name,
        source_url: it.source_url
      });
    } else {
      // fallback
      if (window.TrackerGuide) {
        const src = it.source_url ? `<div style='margin-top:8px;'><a class='cta-link' href='${it.source_url}' target='_blank'>Open the official posting</a></div>` : "";
        TrackerGuide.show(it.agency_name || "How to bid", `<div class='muted'>Quick guidance not available yet.</div>${src}`);
      } else {
        alert("No guide available.");
      }
    }
  }

  function updateStatus(it, newStatus){
    const prev = it.status;
    it.status = newStatus;
    // Update card immediately so badge/text reflect new status without a full reload
    try {
      const card = document.querySelector(`.tracked-card[data-oid="${it.opportunity_id}"]`);
      if (card) {
        const badge = card.querySelector('.status-badge');
        if (badge) badge.textContent = newStatus || 'prospecting';
        const statusLine = Array.from(card.querySelectorAll('.card-list li')).find(li => /Status:/i.test(li.textContent||''));
        if (statusLine) statusLine.innerHTML = `<span class="dot"></span>Status: ${(newStatus||'prospecting')}`;
      }
    } catch(_) {}
    render();
    fetch(`/tracker/${it.opportunity_id}`, {
      method:"PATCH",
      headers:{ "Content-Type":"application/json", "X-CSRF-Token": (getCSRF()||"") },
      body: JSON.stringify({ status:newStatus })
    }).then(res=>{
      if (!res.ok) throw new Error('update failed');
    }).catch(()=>{
      it.status = prev;
      render();
    });
  }

  function removeTracker(it){
    const sel = `.tracked-card[data-oid="${it.opportunity_id}"]`;
    const el = document.querySelector(sel);
    const finish = () => {
      items = items.filter(x => x.opportunity_id !== it.opportunity_id);
      if (el && el.parentNode) {
        el.parentNode.removeChild(el);
        if (!grid.children.length) {
          grid.innerHTML = `<div class="muted">Nothing tracked yet. Go to <a href="/opportunities">Opportunities</a> and click "Track".</div>`;
        }
        updateSummary();
      } else {
        render();
      }
    };
    fetch(`/tracker/${it.opportunity_id}`, { method: "DELETE", headers: { "X-CSRF-Token": (getCSRF()||"") } })
      .catch(()=>{})
      .finally(()=>{
        if (el) {
          el.classList.add('removing');
          setTimeout(finish, 220);
        } else {
          finish();
        }
        // Offer undo
        try {
          showUndo("Removed from dashboard.", async function(){
            try {
              if (it.external_id) {
                await fetch(`/tracker/${it.external_id}/track`, { method: 'POST', credentials: 'include' });
              }
            } catch(_) {}
            try { items.push(it); } catch(_) {}
            render();
          });
        } catch(_) {}
      });
  }

  function showUndo(message, onUndo){
    const id = 'snackbar-undo';
    let bar = document.getElementById(id);
    if (bar) bar.remove();
    bar = document.createElement('div');
    bar.id = id;
    bar.style.position = 'fixed';
    bar.style.bottom = '16px';
    bar.style.right = '16px';
    bar.style.background = '#0f172a';
    bar.style.color = '#fff';
    bar.style.padding = '10px 12px';
    bar.style.borderRadius = '10px';
    bar.style.boxShadow = '0 6px 18px rgba(2,6,23,.25)';
    bar.style.display = 'flex';
    bar.style.gap = '12px';
    bar.style.alignItems = 'center';
    bar.style.zIndex = '10000';
    const span = document.createElement('span');
    span.textContent = message || 'Done';
    const btn = document.createElement('button');
    btn.textContent = 'Undo';
    btn.style.background = '#22c55e';
    btn.style.border = '0';
    btn.style.color = '#0b1220';
    btn.style.borderRadius = '8px';
    btn.style.padding = '6px 10px';
    btn.style.cursor = 'pointer';
    btn.addEventListener('click', function(){ try { onUndo && onUndo(); } catch(_) {} bar.remove(); });
    bar.appendChild(span); bar.appendChild(btn);
    document.body.appendChild(bar);
    setTimeout(()=>{ try { bar.remove(); } catch(_) {} }, 5000);
  }

  function sortItems(arr){
    const mode = selSort.value;
    const byTitle=(a,b)=> (a.title||"").localeCompare(b.title||"");
    const byAgency=(a,b)=> (a.agency_name||"").localeCompare(b.agency_name||"");
    const toTime=v=> v?new Date(v).getTime():Infinity;
    if (mode==="manual") return;
    if (mode==="latest") arr.sort((a,b)=>toTime(b.due_date)-toTime(a.due_date));
    else if (mode==="agency") arr.sort(byAgency);
    else if (mode==="title") arr.sort(byTitle);
    else arr.sort((a,b)=>toTime(a.due_date)-toTime(b.due_date));
  }

  function matchesFilters(it){
    const f1 = selStatus.value ? (it.status||"").toLowerCase() === selStatus.value : true;
    const f2 = selAgency.value ? (it.agency_name||"") === selAgency.value : true;
    const q = (txtSearch && txtSearch.value || "").trim().toLowerCase();
    const f3 = q ? ((it.title||"").toLowerCase().includes(q) || (it.external_id||"").toLowerCase().includes(q) || (it.agency_name||"").toLowerCase().includes(q)) : true;
    return f1 && f2 && f3;
  }

  function updateSummary(view){
    try {
      if (!summaryEl) return;
      const filtered = Array.isArray(view) ? view : items.filter(matchesFilters);
      const shown = filtered.length;
      const total = items.length;
      const soon = filtered.filter(x=> x.due_date && (new Date(x.due_date).getTime() - Date.now()) < 7*24*60*60*1000).length;
      summaryEl.textContent = `${shown}/${total} shown - ${soon} due soon`;
      summaryEl.textContent = summaryEl.textContent.replace(/[^\x20-\x7E-]/g, "-");
    } catch(_) {}
  }
  window.updateDashboardSummary = updateSummary;

  let expandedState = {};

  function render(){
    const view = items.filter(matchesFilters);
    sortItems(view);
    if (selSort.value === 'manual') applyManualOrder(view);
    const out = view.map(it=>{
      const prog = computeProgress(it);
      const filesLabel = (it.file_count||0) === 1 ? "1 file" : `${it.file_count||0} files`;
      const dueMs = it.due_date ? (new Date(it.due_date).getTime() - Date.now()) : null;
      const dueSoon = (dueMs !== null) && (dueMs < 7*24*60*60*1000) && (dueMs >= 0);
      const status = (it.status || "prospecting").toLowerCase();
      const statusStyles = {
        prospecting: { dot: "#126a45", dueBg: "rgba(18,106,69,0.1)", dueText: "#126a45" },
        deciding: { dot: "#b45309", dueBg: "rgba(180,83,9,0.12)", dueText: "#b45309" },
        drafting: { dot: "#2563eb", dueBg: "rgba(37,99,235,0.12)", dueText: "#2563eb" },
        submitted: { dot: "#0f766e", dueBg: "rgba(15,118,110,0.12)", dueText: "#0f766e" },
        won: { dot: "#15803d", dueBg: "rgba(21,128,61,0.14)", dueText: "#15803d" },
        lost: { dot: "#b91c1c", dueBg: "rgba(185,28,28,0.12)", dueText: "#b91c1c" },
      };
      const colors = statusStyles[status] || statusStyles.prospecting;
      const expanded = !!expandedState[it.opportunity_id];
      const trackedBy = (it.tracked_by || "").toString();
      const trackedByLabel = it.is_mine ? "You" : (trackedBy || "Teammate");
      const ringCirc = 2 * Math.PI * 18; // matches 113 in demo
      const dashOffset = ringCirc - (ringCirc * Math.max(0, Math.min(100, prog)) / 100);
      const statusClass = dueSoon ? "status-due-soon" : "";
      return `
        <article class="solicitation-card tracked-card ${statusClass} ${expanded ? 'expanded' : ''}" data-oid="${it.opportunity_id}" tabindex="0" style="--primary:${colors.dot};">
          <div class="solicitation-card-header" data-action="toggle-card" data-oid="${it.opportunity_id}">
            <div class="solicitation-left">
              <div class="status-dot" style="background:${colors.dot};"></div>
              <div class="solicitation-info">
                <div class="solicitation-title" title="${escHtml(it.title||'Untitled')}">${it.title||"Untitled"}</div>
                <div class="solicitation-agency">
                  ${it.agency_name ? `<span class="agency-badge">${escHtml(it.agency_name)}</span>` : ""}
                  ${it.external_id ? `<span class="agency-badge">${escHtml(it.external_id)}</span>` : ""}
                  <span>${filesLabel}</span>
                </div>
              </div>
            </div>
            <div class="solicitation-right">
              <div class="progress-ring tooltip" data-tooltip="${prog}% complete">
                <svg viewBox="0 0 44 44">
                  <circle class="progress-ring-bg" cx="22" cy="22" r="18"/>
                  <circle class="progress-ring-fill" cx="22" cy="22" r="18"
                          stroke="${colors.dot}"
                          stroke-dasharray="${ringCirc}"
                          stroke-dashoffset="${dashOffset}"/>
                </svg>
                <span class="progress-ring-text">${pct(prog)}%</span>
              </div>
              <div class="due-badge" style="background:${colors.dueBg}; color:${colors.dueText}; border:1px solid ${colors.dueBg};">
                <span class="due-icon">🕒</span>
                Due ${dueStr(it.due_date)}
              </div>
              <button class="expand-btn" type="button" data-action="toggle-card" data-oid="${it.opportunity_id}" aria-expanded="${expanded}">⌄</button>
            </div>
          </div>

          <div class="solicitation-details ${expanded ? '' : 'hidden'}">
            <div class="details-divider"></div>
            <div class="details-grid">
              <div class="detail-section checklist">
                <h4>Checklist Progress</h4>
                <ul class="checklist">
                  <li class="done"><span class="check-icon">✓</span>Downloaded RFP documents</li>
                  <li class="done"><span class="check-icon">✓</span>Reviewed requirements</li>
                  <li class="done"><span class="check-icon">✓</span>Prepared pricing sheet</li>
                  <li class="pending"><span class="check-icon">○</span>Final review & submit</li>
                </ul>
              </div>
              <div class="detail-section files">
                <h4>Attached Files</h4>
                <div class="file-chips">
                  <a class="file-chip" href="${it.source_url || "#"}" target="_blank">RFP_Document.pdf</a>
                  <a class="file-chip" href="${it.source_url || "#"}" target="_blank">Pricing_Sheet.xlsx</a>
                  <a class="file-chip" href="${it.source_url || "#"}" target="_blank">Technical_Proposal.docx</a>
                </div>
              </div>
              <div class="detail-section actions">
                <h4>Quick Actions</h4>
                <div class="quick-actions">
                  <button class="action-btn primary" data-action="open-thread" data-oid="${it.opportunity_id}">Submit Proposal</button>
                  <button class="action-btn" data-action="upload" data-oid="${it.opportunity_id}">Upload Document</button>
                  <button class="action-btn" data-action="guide" data-oid="${it.opportunity_id}">View Requirements</button>
                  <button class="action-btn" data-action="open-thread" data-oid="${it.opportunity_id}">Team Thread</button>
                </div>
              </div>
            </div>
          </div>
        </article>
      `;
    });

    grid.innerHTML = out.length ? out.join("") : `<div class="muted">Nothing tracked yet. Go to <a href="/opportunities">Opportunities</a> and click "Track".</div>`;
    updateSummary(view);
  }

  selStatus.addEventListener("change", render);
  selAgency.addEventListener("change", render);
  selSort.addEventListener("change", render);
  // Wire live search + reset + summary if present
  try {
    if (txtSearch) txtSearch.addEventListener('input', render);
    if (btnReset) btnReset.addEventListener('click', function(){
      selStatus.value=''; selAgency.value=''; selSort.value='soonest'; if (txtSearch) txtSearch.value=''; render();
    });
    // augment render to update summary after initial run
    const _render = render;
    render = function(){
      _render();
      try {
        updateSummary();
        // one-time highlight if arriving with ?focus=
        if (!window.__didHighlight) {
          const params = new URLSearchParams(location.search || '');
          const focus = params.get('focus');
          if (focus) {
            const card = document.querySelector(`.tracked-card[data-oid="${focus}"]`);
            if (card) {
              card.classList.add('highlight');
              try { card.scrollIntoView({ behavior:'smooth', block:'start' }); } catch(_) {}
              setTimeout(()=> card.classList.remove('highlight'), 1800);
            }
            window.__didHighlight = true;
          }
        }
      } catch(_){}
    };
  } catch(_){}

  // Persist filters/search in localStorage
  const FILTERS_KEY = 'dashboard_filters_v1';
  function saveFilters(){
    try {
      const data = {
        status: selStatus && selStatus.value || '',
        agency: selAgency && selAgency.value || '',
        sort: selSort && selSort.value || '',
        q: txtSearch && txtSearch.value || ''
      };
      localStorage.setItem(FILTERS_KEY, JSON.stringify(data));
    } catch(_) {}
  }
  function loadFilters(){
    try {
      const raw = localStorage.getItem(FILTERS_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (selStatus && data.status!=null) selStatus.value = data.status;
      if (selAgency && data.agency!=null) selAgency.value = data.agency;
      if (selSort && data.sort!=null) selSort.value = data.sort;
      if (txtSearch && data.q!=null) txtSearch.value = data.q;
    } catch(_) {}
  }
  try {
    loadFilters();
    ['change','input'].forEach(evt=>{
      if (selStatus) selStatus.addEventListener(evt, saveFilters);
      if (selAgency) selAgency.addEventListener(evt, saveFilters);
      if (selSort) selSort.addEventListener(evt, saveFilters);
      if (txtSearch) txtSearch.addEventListener(evt, saveFilters);
    });
  } catch(_) {}

  // Keyboard reorder fallback: Shift/Alt + ArrowUp/ArrowDown moves card
  grid.addEventListener('keydown', function(ev){
    const card = ev.target && ev.target.closest && ev.target.closest('.tracked-card');
    if (!card) return;
    if (!(ev.key==='ArrowUp' || ev.key==='ArrowDown')) return;
    if (!(ev.shiftKey || ev.altKey)) return; // require a modifier to avoid stealing navigation
    ev.preventDefault();
    const oid = card.getAttribute('data-oid');
    const all = Array.from(grid.querySelectorAll('.tracked-card'));
    const idx = all.indexOf(card);
    if (idx < 0) return;
    if (ev.key==='ArrowUp' && idx>0){ grid.insertBefore(card, all[idx-1]); }
    if (ev.key==='ArrowDown' && idx<all.length-1){ grid.insertBefore(card, all[idx+1].nextSibling); }
    const order = Array.from(grid.querySelectorAll('.tracked-card')).map(el=> el.getAttribute('data-oid'));
    if (selSort && selSort.value !== 'manual') selSort.value = 'manual';
    saveOrder(order);
  });

  // Populate Agencies filter dynamically from items if options look minimal
  try {
    if (selAgency && selAgency.options && selAgency.options.length <= 2) {
      const set = new Set();
      items.forEach(it => { const v = (it.agency_name||'').trim(); if (v) set.add(v); });
      Array.from(set).sort().forEach(v => {
        const opt = document.createElement('option'); opt.value = v; opt.textContent = v; selAgency.appendChild(opt);
      });
    }
  } catch(_){}
  // Event delegation for card actions
  grid.addEventListener("click", function(e){
    const btn = e.target.closest('[data-action]');
    if (!btn || !grid.contains(btn)) return;
    const action = btn.getAttribute('data-action');
    const oid = btn.getAttribute('data-oid') || (btn.closest('.tracked-card') && btn.closest('.tracked-card').getAttribute('data-oid'));
    if (!oid) return;
    const it = items.find(x => String(x.opportunity_id) === String(oid));
    if (!it) return;
    if (action === 'toggle-card') {
      expandedState[oid] = !expandedState[oid];
      render();
      return;
    }
    if (action === 'toggle-collab') {
      toggleCollab(oid);
      if (collabState.open[oid]) {
        ensureNotes(oid).finally(render);
      } else {
        render();
      }
      return;
    }
    if (action === 'open-thread') {
      ensureNotes(oid).finally(()=> openThread(threadMetaFromItem(it) || { opportunity_id: oid }));
      return;
    }
    if (action === 'add-note') {
      const textarea = btn.closest('.collab-box') && btn.closest('.collab-box').querySelector('textarea[data-action="note-text"]');
      const val = textarea ? textarea.value : "";
      if (!val || !val.trim()) return;
      postNote(oid, val).then(()=> {
        if (textarea) textarea.value = "";
        render();
        openThread(threadMetaFromItem(it) || { opportunity_id: oid });
      }).catch(()=>{});
      return;
    }
    if (action === 'remove') return removeTracker(it);
    if (action === 'upload') return openUploads(it);
    if (action === 'guide') return openGuide(it);
  });

  grid.addEventListener("change", function(e){
    const sel = e.target.closest('select[data-action="status"]');
    if (sel && grid.contains(sel)) {
      const oid = sel.getAttribute('data-oid');
      const it = items.find(x => String(x.opportunity_id) === String(oid));
      if (it) updateStatus(it, sel.value);
      return;
    }
    const assign = e.target.closest('input[data-action="assign"]');
    if (assign && grid.contains(assign)) {
      const oid = assign.getAttribute('data-oid');
      // TODO: Implement server-side assignee sync; for now local state only
      setAssignee(oid, assign.value);
    }
  });
  // Hide any legacy top upload block by default, if present
  try {
    const labels = Array.from(document.querySelectorAll('.label'));
    const lbl = labels.find(el => /Upload files to a tracked solicitation/i.test(el.textContent||''));
    const c = lbl ? lbl.closest('.card') : null;
    if (c) c.style.display = 'none';
  } catch(_) {}
  // Initial render (sync order from server first)
  (async function(){ await syncOrderFromServer(); render(); setupCardDnD(); })();

  // Drag-and-drop by grabbing the entire card (not a grip)
  function setupCardDnD(){
    // Add manual option if missing
    if (selSort && !Array.from(selSort.options).some(o=>o.value==='manual')){
      const opt = document.createElement('option'); opt.value='manual'; opt.textContent='Manual (drag to sort)'; selSort.appendChild(opt);
    }
    // Mark cards draggable after each render
    const markDraggable = () => {
      Array.from(document.querySelectorAll('.tracked-card')).forEach(card=>{
        card.setAttribute('draggable','true');
      });
    };
    markDraggable();

    let dndWired = false;
    if (dndWired) return; // safety
    dndWired = true;
    let draggingId = null;
    const isInteractive = (el) => !!el && !!el.closest('a,button,input,textarea,select,[contenteditable="true"]');
    grid.addEventListener('dragstart', function(ev){
      const card = ev.target.closest('.tracked-card');
      if (!card) return;
      if (isInteractive(ev.target)) { try { ev.preventDefault(); } catch(_) {} return; }
      draggingId = card.getAttribute('data-oid');
      card.classList.add('dragging');
      try { ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', draggingId); } catch(_) {}
    });
    grid.addEventListener('dragend', function(ev){
      const card=ev.target.closest('.tracked-card'); if(card) card.classList.remove('dragging');
      draggingId=null;
      Array.from(document.querySelectorAll('.drop-before, .drop-after')).forEach(el=>el.classList.remove('drop-before','drop-after'));
      const order = Array.from(grid.querySelectorAll('.tracked-card')).map(el=> el.getAttribute('data-oid'));
      saveOrder(order);
    });
    grid.addEventListener('dragover', function(ev){
      if(!draggingId) return; ev.preventDefault();
      const over=ev.target.closest('.tracked-card');
      if(!over || over.getAttribute('data-oid')===draggingId) return;
      const from = grid.querySelector(`.tracked-card[data-oid="${draggingId}"]`);
      if(!from) return;
      const r = over.getBoundingClientRect();
      const vertical = (ev.clientY - r.top) < (r.height/2);
      if (vertical) {
        over.parentNode.insertBefore(from, over);
      } else {
        over.parentNode.insertBefore(from, over.nextSibling);
      }
      Array.from(document.querySelectorAll('.drop-before, .drop-after')).forEach(el=>el.classList.remove('drop-before','drop-after'));
      over.classList.add(vertical ? 'drop-before' : 'drop-after');
    });
    grid.addEventListener('drop', function(ev){
      if(!draggingId) return; ev.preventDefault();
      Array.from(document.querySelectorAll('.drop-before, .drop-after')).forEach(el=>el.classList.remove('drop-before','drop-after'));
      if (selSort && selSort.value !== 'manual') selSort.value = 'manual';
      const order = Array.from(grid.querySelectorAll('.tracked-card')).map(el=> el.getAttribute('data-oid'));
      saveOrder(order);
    });

    // Re-mark draggable after every render call
    const _render = render;
    render = function(){ _render(); markDraggable(); };
  }

  // Drawer controller (used by vendor.js, too)
  window.TrackerGuide = {
    show(agency, html) {
      document.getElementById("guide-agency").textContent = agency || "";
      document.getElementById("guide-title").textContent = "How to bid";
      document.getElementById("guide-content").innerHTML = html || "";
      document.getElementById("guide-overlay").style.display = "block";
      document.getElementById("guide-drawer").setAttribute("aria-hidden", "false");
    },
    close() {
      document.getElementById("guide-overlay").style.display = "none";
      document.getElementById("guide-drawer").setAttribute("aria-hidden", "true");
    }
  };
})();
















