// Public action from the table
async function trackAndOpenUploads(opportunityId){
  await fetch(`/tracker/${opportunityId}/track`,{method:"POST"});
  document.getElementById("opp-id").value = opportunityId;
  openDrawer();
  await refreshFileList(opportunityId);
}

// Drawer helpers
function openDrawer(){ document.getElementById("bid-drawer").classList.remove("hidden"); }
function closeDrawer(){ document.getElementById("bid-drawer").classList.add("hidden"); }

// File list
async function refreshFileList(opportunityId){
  const ul = document.getElementById("file-list");
  ul.innerHTML = "<li>Loading…</li>";
  try{
    const res = await fetch(`/uploads/list/${opportunityId}`);
    if(!res.ok) throw new Error("Failed");
    const rows = await res.json();
    if(!rows.length){ ul.innerHTML = "<li class='muted'>No files yet.</li>"; return; }
    ul.innerHTML = "";
    rows.forEach(row=>{
      const li = document.createElement("li");
      const sizeKB = row.size ? Math.round(row.size/1024) : 0;
      li.innerHTML = `
        <span>${row.filename} <span style="opacity:.6;">(${sizeKB} KB)</span></span>
        <span>
          <a href="${row.download_url}" target="_blank" rel="noopener">Download</a>
          <button style="margin-left:8px;" onclick="deleteUpload(${row.id}, ${opportunityId})">Delete</button>
        </span>`;
      ul.appendChild(li);
    });
  }catch(e){ ul.innerHTML = "<li>Failed to load.</li>"; }
}

async function deleteUpload(uploadId, opportunityId){
  if(!confirm("Delete this file?")) return;
  const res = await fetch(`/uploads/${uploadId}`,{method:"DELETE"});
  if(res.ok) refreshFileList(opportunityId);
}

// Uploads
async function uploadFiles(opportunityId, files){
  if(!files || !files.length) return;
  const fd = new FormData();
  fd.append("opportunity_id", opportunityId);
  for(let f of files) fd.append("files", f);
  const res = await fetch("/uploads/add",{method:"POST",body:fd});
  if(!res.ok){ alert("Upload failed."); return; }
  await refreshFileList(opportunityId);
}

async function downloadZip(){
  const oppId = document.getElementById("opp-id").value;
  window.open(`/zip/${oppId}`,"_blank");
}

// Drag & Drop wiring
function initBidTrackerUI(){
  const dropzone = document.getElementById("dropzone");
  const browseBtn = document.getElementById("browse-btn");
  const fileInput = document.getElementById("file-input");
  const form = document.getElementById("upload-form");
  if(!dropzone || !browseBtn || !fileInput || !form) return;

  browseBtn.addEventListener("click", ()=> fileInput.click());
  fileInput.addEventListener("change", async ()=>{
    const oppId = document.getElementById("opp-id").value;
    await uploadFiles(oppId, fileInput.files);
    fileInput.value = "";
  });

  ["dragenter","dragover","dragleave","drop"].forEach(evt=>{
    dropzone.addEventListener(evt, e=>{ e.preventDefault(); e.stopPropagation(); });
  });
  ["dragenter","dragover"].forEach(evt=>{
    dropzone.addEventListener(evt, ()=> dropzone.classList.add("dragover"));
  });
  ["dragleave","drop"].forEach(evt=>{
    dropzone.addEventListener(evt, ()=> dropzone.classList.remove("dragover"));
  });
  dropzone.addEventListener("drop", async e=>{
    const oppId = document.getElementById("opp-id").value;
    const files = e.dataTransfer?.files || [];
    if(!files.length) return;
    await uploadFiles(oppId, files);
  });

  form.addEventListener("submit", async e=>{
    e.preventDefault();
    const oppId = document.getElementById("opp-id").value;
    await uploadFiles(oppId, fileInput.files);
    fileInput.value = "";
  });
}

document.addEventListener("DOMContentLoaded", initBidTrackerUI);
