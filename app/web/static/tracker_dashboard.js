(function () {
  const grid = document.getElementById("tracked-grid");
  const items = JSON.parse(grid.getAttribute("data-items") || "[]");

  const selStatus = document.getElementById("status-filter");
  const selAgency = document.getElementById("agency-filter");
  const selSort   = document.getElementById("sort-by");

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

  function openUploads(it){
    if (window.trackAndOpenUploads) window.trackAndOpenUploads(it.external_id);
    else alert("Upload drawer not loaded.");
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
    fetch(`/tracker/${it.opportunity_id}`, {
      method:"PATCH",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ status:newStatus })
    }).then(()=>render());
  }

  function sortItems(arr){
    const mode = selSort.value;
    const byTitle=(a,b)=> (a.title||"").localeCompare(b.title||"");
    const byAgency=(a,b)=> (a.agency_name||"").localeCompare(b.agency_name||"");
    const toTime=v=> v?new Date(v).getTime():Infinity;
    if (mode==="latest") arr.sort((a,b)=>toTime(b.due_date)-toTime(a.due_date));
    else if (mode==="agency") arr.sort(byAgency);
    else if (mode==="title") arr.sort(byTitle);
    else arr.sort((a,b)=>toTime(a.due_date)-toTime(b.due_date));
  }

  function matchesFilters(it){
    const f1 = selStatus.value ? (it.status||"").toLowerCase() === selStatus.value : true;
    const f2 = selAgency.value ? (it.agency_name||"") === selAgency.value : true;
    return f1 && f2;
  }

  function render(){
    const view = items.filter(matchesFilters);
    sortItems(view);
    const out = view.map(it=>{
      const prog = computeProgress(it);
      const filesLabel = (it.file_count||0) === 1 ? "1 file" : `${it.file_count||0} files`;
      return `
        <article class="tracked-card" data-oid="${it.opportunity_id}">
          <div class="top">
            <div>
              <div class="title">${it.title||"Untitled"}</div>
              <div class="meta">
                <span>${it.external_id||"—"}</span><span>•</span>
                <span>${it.agency_name||""}</span><span>•</span>
                <span>Due: ${dueStr(it.due_date)}</span><span>•</span>
                <span>${filesLabel}</span>
              </div>
            </div>
            ${statusBadge(it.status)}
          </div>

          <div class="progress"><div style="width:${pct(prog)}%; background:linear-gradient(90deg,#6366f1,#22d3ee)"></div></div>

          <ul class="card-list">
            <li><span class="dot"></span>Type: ${it.category||"—"}</li>
            <li><span class="dot"></span>Status: ${(it.status||"prospecting")}</li>
          </ul>

          <div class="actions">
            <button class="btn" onclick='(${openUploads})((${JSON.stringify(it)}))'>Upload files</button>
            <button class="btn-secondary" onclick='(${openGuide})((${JSON.stringify(it)}))'>How to bid</button>
            <a class="btn-secondary" href="${it.source_url || "#"}" target="_blank">Source</a>
            <select onchange='(${updateStatus})((${JSON.stringify(it)}), this.value)'>
              ${["prospecting","deciding","drafting","submitted","won","lost"].map(s=>`<option value="${s}" ${((it.status||"prospecting")===s?"selected":"")}>${s[0].toUpperCase()+s.slice(1)}</option>`).join("")}
            </select>
          </div>
        </article>
      `;
    });

    grid.innerHTML = out.length ? out.join("") : `<div class="muted">Nothing tracked yet. Go to <a href="/opportunities">Opportunities</a> and click “Track & Upload”.</div>`;
  }

  selStatus.addEventListener("change", render);
  selAgency.addEventListener("change", render);
  selSort.addEventListener("change", render);
  render();

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
