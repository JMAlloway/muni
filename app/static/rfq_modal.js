async function openDetailModal(rfqId, agencyName){
  const overlay = document.getElementById("rfq-modal-overlay");
  const content = document.getElementById("rfq-modal-content");
  overlay.style.display = "flex";
  content.innerHTML = "<div style='font-size:14px;color:#555;'>Loading...</div>";

  let endpoint = "";
  if(agencyName && agencyName.toLowerCase().includes("cota")) endpoint = "/cota_detail/"+encodeURIComponent(rfqId);
  else if(agencyName && agencyName.toLowerCase().includes("columbus")) endpoint = "/columbus_detail/"+encodeURIComponent(rfqId);
  else if(agencyName && agencyName.toLowerCase().includes("gahanna")) endpoint = "/gahanna_detail/"+encodeURIComponent(rfqId);
  else endpoint = "/columbus_detail/"+encodeURIComponent(rfqId);

  try{
    const resp = await fetch(endpoint);
    if(!resp.ok){ content.innerHTML = "<div style='color:#b91c1c;'>Unable to load details.</div>"; return; }
    const data = await resp.json();
    const safe = v => (v ? String(v) : "");
    if(data.error){
      content.innerHTML = `
        <div style="color:#b91c1c;font-weight:600;margin-bottom:.5rem;">Unable to load full opportunity details.</div>
        <div style="font-size:.8rem;color:#666;white-space:pre-wrap;max-height:200px;overflow-y:auto;border:1px solid #eee;padding:.5rem;border-radius:4px;background:#fafafa;">
          ${safe(data.error)} ${safe(data.status_code ? "Status "+data.status_code : "")} ${safe(data.text || "")}
        </div>`;
      return;
    }
    // TODO: render details…
  }catch(err){
    content.innerHTML = "<div style='color:#b91c1c;'>Error loading details.</div>";
  }
}
function closeDetailModal(){
  document.getElementById("rfq-modal-overlay").style.display = "none";
}
