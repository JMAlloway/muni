async function openDetailModal(rfqId, agencyName){
  const overlay = document.getElementById("rfq-modal-overlay");
  const content = document.getElementById("rfq-modal-content");
  overlay.style.display = "flex";
  content.innerHTML = "<div style='font-size:14px;color:#555;'>Loading...</div>";

  // Choose endpoint based on agency
  const a = (agencyName||"").toLowerCase();
  let endpoint = "/columbus_detail/"+encodeURIComponent(rfqId);
  if (a.includes("cota")) endpoint = "/cota_detail/"+encodeURIComponent(rfqId);
  else if (a.includes("gahanna")) endpoint = "/gahanna_detail/"+encodeURIComponent(rfqId);

  try {
    const resp = await fetch(endpoint);
    if (!resp.ok) { content.innerHTML = "<div style='color:#b91c1c;'>Unable to load details.</div>"; return; }
    const data = await resp.json();
    const safe = v => (v ? String(v) : "");

    if (data && data.error) {
      content.innerHTML = `
        <div style="color:#b91c1c;font-weight:600;margin-bottom:.5rem;">Unable to load full opportunity details.</div>
        <div style="font-size:.8rem;color:#666;white-space:pre-wrap;max-height:200px;overflow-y:auto;border:1px solid #eee;padding:.5rem;border-radius:4px;background:#fafafa;">
          ${safe(data.error)} ${safe(data.status_code ? "Status "+data.status_code : "")} ${safe(data.text || "")}
        </div>`;
      return;
    }

    const title  = safe(data.title || data.rfq_id || rfqId);
    const agency = agencyName || "City of Columbus";
    const due    = safe(data.due_date || "TBD");
    const posted = safe(data.posted_date || "");
    const dept   = safe(data.department || "");
    const type   = safe(data.solicitation_type || "");
    const status = safe(data.status_text || "");
    const source = safe(data.source_url || "");

    let headerHtml = `
      <h2 style="margin:0 0 6px 0;font-size:18px;">${title}</h2>
      <div style="color:#64748b;font-size:12px;margin-bottom:10px;">
        <span>${agency}</span>
        ${dept ? ' · <span>'+dept+'</span>' : ''}
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
        <span class="pill"><b>Due:</b> ${due}</span>
        ${posted ? '<span class="pill"><b>Posted:</b> '+posted+'</span>' : ''}
        ${type ? '<span class="pill">'+type+'</span>' : ''}
        ${status ? '<span class="pill">'+status+'</span>' : ''}
      </div>
      ${source ? '<a class="cta-link" href="'+source+'" target="_blank" rel="noopener">View original source</a>' : ''}
    `;

    if (data.scope_text) {
      headerHtml += `<div style="font-size:14px;line-height:1.5;margin:12px 0;">${safe(data.scope_text)}</div>`;
    }

    let attachHtml = "";
    let itemsHtml = "";
    const headerId = data.rfq_header_id;
    if (headerId) {
      try {
        const [ar, ir] = await Promise.all([
          fetch(`/columbus_detail/${encodeURIComponent(headerId)}/attachments`),
          fetch(`/columbus_detail/${encodeURIComponent(headerId)}/items`),
        ]);
        if (ar.ok) {
          const aj = await ar.json();
          if (Array.isArray(aj.attachments) && aj.attachments.length) {
            attachHtml = `<div style="margin:10px 0 0 0;"><b>Attachments</b><ul style="margin:6px 0 0 18px;">`
              + aj.attachments.map(f => `<li><a href="${safe(f.url)}" target="_blank" rel="noopener">${safe(f.filename)}</a></li>`).join("")
              + `</ul></div>`;
          }
        }
        if (ir.ok) {
          const ij = await ir.json();
          if (Array.isArray(ij.items) && ij.items.length) {
            itemsHtml = `<div style="margin:12px 0 0 0;"><b>Line items</b><ul style="margin:6px 0 0 18px;">`
              + ij.items.map(it => `<li>${safe(it.line_no||'—')}: ${safe(it.name||'')}${it.desc?(' — '+safe(it.desc)) : ''} ${it.qty?('('+safe(it.qty)+' '+safe(it.uom||'')+')'):''}</li>`).join("")
              + `</ul></div>`;
          }
        }
      } catch (_) { /* ignore */ }
    }

    content.innerHTML = `<div>${headerHtml}${attachHtml}${itemsHtml}</div>`;
  } catch (err) {
    content.innerHTML = "<div style='color:#b91c1c;'>Error loading details.</div>";
  }
}

function closeDetailModal(){
  document.getElementById("rfq-modal-overlay").style.display = "none";
}
