(function () {
  const getCSRF = () => {
    try {
      return (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || "";
    } catch (_) {
      return "";
    }
  };

  const kbListEl = document.getElementById("kbList");
  const refreshBtn = document.getElementById("refreshDocs");
  const uploadForm = document.getElementById("kbUploadForm");
  const kbDocType = document.getElementById("kbDocType");
  const kbTags = document.getElementById("kbTags");
  const kbFiles = document.getElementById("kbFiles");
  const selectAllDocsBtn = document.getElementById("selectAllDocs");
  const clearDocsBtn = document.getElementById("clearDocs");
  const genForm = document.getElementById("genForm");
  const genOpportunity = document.getElementById("genOpportunity");
  const genInstructions = document.getElementById("genInstructions");
  const uploadsList = document.getElementById("uploadsList");
  const refreshUploads = document.getElementById("refreshUploads");
  const addSectionBtn = document.getElementById("addSection");
  const sectionsList = document.getElementById("sectionsList");
  const secQuestion = document.getElementById("secQuestion");
  const secMaxWords = document.getElementById("secMaxWords");
  const secRequired = document.getElementById("secRequired");
  const resultsEl = document.getElementById("results");
  const resultsClear = document.getElementById("resultsClear");
  const summaryCard = document.getElementById("summaryCard");
  const checklistEl = document.getElementById("checklist");
  const instructionsBlock = document.getElementById("instructionsBlock");
  const generateDocsBtn = document.getElementById("generateDocs");
  const docsContainer = document.getElementById("docsContainer");
  const regenSummaryBtn = document.getElementById("regenSummary");
  const coverEdit = document.getElementById("coverEdit");
  const soqEdit = document.getElementById("soqEdit");
  const exportWordBtn = document.getElementById("exportWord");
  const exportPdfBtn = document.getElementById("exportPdf");
  const overlay = document.createElement("div");
  overlay.className = "loading-overlay";
  overlay.innerHTML = `<div class="spinner"></div><div class="loading-text">Working...</div>`;
  document.body.appendChild(overlay);

  const state = {
    docs: [],
    selectedDocs: new Set(),
    uploads: [],
    selectedUploads: new Set(),
    sections: [],
    loading: false,
    extracted: null,
    coverDraft: "",
    soqDraft: "",
  };

  function setLoading(flag) {
    state.loading = flag;
    if (flag) {
      document.body.classList.add("is-loading");
      overlay.style.display = "flex";
    } else {
      document.body.classList.remove("is-loading");
      overlay.style.display = "none";
    }
  }

  async function fetchDocs() {
    try {
      const res = await fetch("/api/knowledge/list", { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load docs");
      const data = await res.json();
      state.docs = Array.isArray(data) ? data : [];
      renderDocs();
    } catch (err) {
      console.error(err);
      kbListEl.innerHTML = `<div class="empty">Unable to load documents</div>`;
    }
  }

  function renderDocs() {
    if (!kbListEl) return;
    if (!state.docs.length) {
      kbListEl.innerHTML = `<div class="empty">No knowledge documents yet.</div>`;
      return;
    }
    kbListEl.innerHTML = "";
    state.docs.forEach((doc) => {
      const card = document.createElement("div");
      card.className = "kb-item";
      const checked = state.selectedDocs.has(doc.id) ? "checked" : "";
      card.innerHTML = `
        <label class="checkbox">
          <input type="checkbox" data-id="${doc.id}" ${checked}>
          <span></span>
        </label>
        <div class="meta">
          <div class="title">${doc.filename || "Untitled"}</div>
          <div class="tags">${(doc.tags || []).map((t) => `<span class="tag">${t}</span>`).join("")}</div>
          <div class="status pill ${doc.extraction_status || ""}">${doc.extraction_status || "pending"}</div>
        </div>
        <div class="actions">
          <button class="ghost-btn" data-action="preview" data-id="${doc.id}">Preview</button>
          <button class="ghost-btn" data-action="extract" data-id="${doc.id}">Extract</button>
          <button class="ghost-btn danger" data-action="delete" data-id="${doc.id}">Delete</button>
        </div>
      `;
      kbListEl.appendChild(card);
    });
  }

  async function fetchTracked() {
    const sel = genOpportunity;
    if (!sel) return;
    try {
      const res = await fetch("/api/tracked/my", { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load tracked");
      const data = await res.json();
      sel.innerHTML = `<option value="">Select a tracked solicitation</option>`;
      (Array.isArray(data) ? data : []).forEach((row) => {
        const opt = document.createElement("option");
        opt.value = row.id;
        const due = row.due_date ? ` | due ${row.due_date}` : "";
        const agency = row.agency_name ? ` | ${row.agency_name}` : "";
        opt.textContent = `${row.title || row.id}${agency}${due}`;
        sel.appendChild(opt);
      });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchExtraction() {
    const sel = genOpportunity;
    if (!sel || !sel.value) {
      state.extracted = null;
      renderSummary();
      return;
    }
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(sel.value)}/extracted`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed extraction fetch");
      const data = await res.json();
      state.extracted = data;
      renderSummary();
    } catch (err) {
      console.error(err);
      state.extracted = null;
      renderSummary();
    }
  }

  function renderSummary() {
    if (summaryCard) {
      if (!state.extracted) {
        summaryCard.classList.add("empty");
        summaryCard.textContent = "Select an opportunity to load extracted summary.";
      } else {
        summaryCard.classList.remove("empty");
        const ex = state.extracted.extracted || {};
        summaryCard.innerHTML = `
          <h3>${state.extracted.title || "Untitled"}</h3>
          <div class="hint">${state.extracted.agency || ""}</div>
          <p>${state.extracted.summary || ex.summary || "No summary"}</p>
          <div class="hint">${ex.scope_of_work || ""}</div>
        `;
      }
    }

    if (checklistEl) {
      checklistEl.innerHTML = "";
      if (!state.extracted || !state.extracted.extracted) {
        checklistEl.innerHTML = `<li class="hint">No data.</li>`;
      } else {
        const ex = state.extracted.extracted;
        const lists = [
          ...(ex.required_documents || []),
          ...(ex.required_forms || []),
          ...(ex.compliance_terms || []),
          ...(ex.contractor_requirements || []),
          ...(ex.training_requirements || []),
        ];
        if (!lists.length) {
          checklistEl.innerHTML = `<li class="hint">No checklist items found.</li>`;
        } else {
          lists.forEach((item) => {
            const li = document.createElement("li");
            li.textContent = item;
            checklistEl.appendChild(li);
          });
        }
      }
    }

    if (instructionsBlock) {
      if (!state.extracted || !state.extracted.extracted) {
        instructionsBlock.innerHTML = `<p class="hint">No submission instructions yet.</p>`;
      } else {
        const ex = state.extracted.extracted;
        const instr = ex.submission_instructions || "No submission instructions found.";
        instructionsBlock.innerHTML = `<p>${instr}</p>`;
      }
    }
  }

  async function generateDocs() {
    if (!genOpportunity || !genOpportunity.value) {
      alert("Select an opportunity first.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(genOpportunity.value)}/generate`, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRF-Token": getCSRF(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ instruction_upload_ids: Array.from(state.selectedUploads) }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `HTTP ${res.status}`);
      }
      const data = await res.json();
      renderDocs(data.documents || {});
    } catch (err) {
      alert("Generation failed: " + err);
    } finally {
      setLoading(false);
    }
  }

  async function regenerateSummary() {
    if (!genOpportunity || !genOpportunity.value) {
      alert("Select an opportunity first.");
      return;
    }
    if (!state.selectedUploads.size) {
      alert("Select at least one uploaded RFP file to extract.");
      return;
    }
    setLoading(true);
    try {
      // Re-extract from selected uploads (first one sufficient for now)
      const uploadIds = Array.from(state.selectedUploads);
      for (const uid of uploadIds) {
        await fetch(`/api/rfp-extract/${uid}`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": getCSRF() },
        });
      }
      await fetchExtraction();

      // Generate docs to populate checklist/instructions in UI
      const res = await fetch(`/api/opportunities/${encodeURIComponent(genOpportunity.value)}/generate`, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRF-Token": getCSRF(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ instruction_upload_ids: Array.from(state.selectedUploads) }),
      });
      if (res.ok) {
        const data = await res.json();
        const docs = data.documents || {};
        const ex = state.extracted?.extracted || {};
        if (docs.submission_instructions) {
          ex.submission_instructions = docs.submission_instructions;
        }
        if (Array.isArray(docs.checklist)) {
          ex.required_documents = docs.checklist;
        }
        state.extracted = { ...(state.extracted || {}), extracted: ex };
        renderSummary();
        renderDocs(docs);
      }
    } catch (err) {
      alert("Generation failed: " + err);
    } finally {
      setLoading(false);
    }
  }

  function renderDocs(docs) {
    if (!docsContainer) return;
    docsContainer.classList.remove("empty");
    const cover = docs.cover_letter || "";
    const soq = docs.soq || {};
    const checklist = docs.submission_checklist || docs.checklist || [];
    const events = docs.calendar_events || [];

    const toText = (val) => {
      if (Array.isArray(val)) {
        return val
          .map((v) => {
            if (v && typeof v === "object") return JSON.stringify(v, null, 2);
            return String(v || "");
          })
          .join("\n");
      }
      if (val && typeof val === "object") {
        return JSON.stringify(val, null, 2);
      }
      return String(val || "");
    };

    function download(name, content) {
      const blob = new Blob([content || ""], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    }

    docsContainer.innerHTML = `
      <article class="result">
        <div class="result-head">
          <h4>Cover letter</h4>
          <button class="ghost-btn" data-dl="cover">Download</button>
        </div>
        <div class="result-body">${(cover || "").replace(/\\n/g, "<br>")}</div>
      </article>
      <article class="result">
        <div class="result-head">
          <h4>Statement of Qualifications</h4>
          <button class="ghost-btn" data-dl="soq">Download</button>
        </div>
        <div class="result-body">
          <strong>Cover page</strong><br>${toText(soq.cover_page).replace(/\\n/g, "<br>")}<br><br>
          <strong>Company overview</strong><br>${toText(soq.company_overview).replace(/\\n/g, "<br>")}<br><br>
          <strong>Legal structure</strong><br>${toText(soq.legal_structure).replace(/\\n/g, "<br>")}<br><br>
          <strong>Certifications</strong><br>${toText(soq.business_certifications).replace(/\\n/g, "<br>")}<br><br>
          <strong>Programs served</strong><br>${toText(soq.programs_served).replace(/\\n/g, "<br>")}<br><br>
          <strong>Criminal history policy</strong><br>${toText(soq.criminal_history_policy).replace(/\\n/g, "<br>")}<br><br>
          <strong>Recordkeeping controls</strong><br>${toText(soq.recordkeeping_controls).replace(/\\n/g, "<br>")}<br><br>
          <strong>Project manager</strong><br>${toText(soq.project_manager).replace(/\\n/g, "<br>")}<br><br>
          <strong>Key personnel</strong><br>${toText(soq.key_personnel).replace(/\\n/g, "<br>")}<br><br>
          <strong>Organizational capacity</strong><br>${toText(soq.organizational_capacity).replace(/\\n/g, "<br>")}<br><br>
          <strong>Relevant projects</strong><br>${toText(soq.relevant_projects).replace(/\\n/g, "<br>")}<br><br>
          <strong>Low-income programs</strong><br>${toText(soq.low_income_programs).replace(/\\n/g, "<br>")}<br><br>
          <strong>Timelines</strong><br>${toText(soq.timelines).replace(/\\n/g, "<br>")}<br><br>
          <strong>Contractor licenses</strong><br>${toText(soq.contractor_licenses).replace(/\\n/g, "<br>")}<br><br>
          <strong>Trainings completed</strong><br>${toText(soq.trainings_completed).replace(/\\n/g, "<br>")}<br><br>
          <strong>Certifications</strong><br>${toText(soq.certifications).replace(/\\n/g, "<br>")}<br><br>
          <strong>Training plan</strong><br>${toText(soq.training_plan).replace(/\\n/g, "<br>")}<br><br>
          <strong>Insurance</strong><br>${toText(soq.insurance).replace(/\\n/g, "<br>")}<br><br>
          <strong>Compliance statements</strong><br>${toText(soq.compliance_statements).replace(/\\n/g, "<br>")}<br><br>
          <strong>Appendices</strong><br>${toText(soq.appendices).replace(/\\n/g, "<br>")}
        </div>
      </article>
      <article class="result">
        <div class="result-head"><h4>Checklist</h4></div>
        <div class="result-body">${(checklist || []).map((c) => `<div>- ${c}</div>`).join("")}</div>
      </article>
      <article class="result">
        <div class="result-head"><h4>Calendar events</h4></div>
        <div class="result-body">${(events || []).map((e) => `<div>${e.title || ""} ${e.due_date || ""} ${e.notes || ""}</div>`).join("")}</div>
      </article>
    `;

    docsContainer.querySelectorAll("[data-dl]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-dl");
        if (kind === "cover") {
          download("cover_letter.txt", cover);
        }
        if (kind === "soq") {
          const text = `
COVER PAGE
${toText(soq.cover_page)}

COMPANY OVERVIEW
${toText(soq.company_overview)}

LEGAL STRUCTURE
${toText(soq.legal_structure)}

BUSINESS CERTIFICATIONS
${toText(soq.business_certifications)}

PROGRAMS SERVED
${toText(soq.programs_served)}

CRIMINAL HISTORY POLICY
${toText(soq.criminal_history_policy)}

RECORDKEEPING CONTROLS
${toText(soq.recordkeeping_controls)}

PROJECT MANAGER
${toText(soq.project_manager)}

KEY PERSONNEL
${toText(soq.key_personnel)}

ORGANIZATIONAL CAPACITY
${toText(soq.organizational_capacity)}

RELEVANT PROJECTS
${toText(soq.relevant_projects)}

LOW INCOME PROGRAMS
${toText(soq.low_income_programs)}

TIMELINES
${toText(soq.timelines)}

CONTRACTOR LICENSES
${toText(soq.contractor_licenses)}

TRAININGS COMPLETED
${toText(soq.trainings_completed)}

CERTIFICATIONS
${toText(soq.certifications)}

TRAINING PLAN
${toText(soq.training_plan)}

INSURANCE
${toText(soq.insurance)}

COMPLIANCE STATEMENTS
${toText(soq.compliance_statements)}

APPENDICES
${toText(soq.appendices)}
`;
          download("soq.txt", text);
        }
      });
    });

    state.coverDraft = toText(cover);
    state.soqDraft = toText(`
COVER PAGE
${toText(soq.cover_page)}

COMPANY OVERVIEW
${toText(soq.company_overview)}

LEGAL STRUCTURE
${toText(soq.legal_structure)}

BUSINESS CERTIFICATIONS
${toText(soq.business_certifications)}

PROGRAMS SERVED
${toText(soq.programs_served)}

CRIMINAL HISTORY POLICY
${toText(soq.criminal_history_policy)}

RECORDKEEPING CONTROLS
${toText(soq.recordkeeping_controls)}

PROJECT MANAGER
${toText(soq.project_manager)}

KEY PERSONNEL
${toText(soq.key_personnel)}

ORGANIZATIONAL CAPACITY
${toText(soq.organizational_capacity)}

RELEVANT PROJECTS
${toText(soq.relevant_projects)}

LOW INCOME PROGRAMS
${toText(soq.low_income_programs)}

TIMELINES
${toText(soq.timelines)}

CONTRACTOR LICENSES
${toText(soq.contractor_licenses)}

TRAININGS COMPLETED
${toText(soq.trainings_completed)}

CERTIFICATIONS
${toText(soq.certifications)}

TRAINING PLAN
${toText(soq.training_plan)}

INSURANCE
${toText(soq.insurance)}

COMPLIANCE STATEMENTS
${toText(soq.compliance_statements)}

APPENDICES
${toText(soq.appendices)}
`);

    renderEditableDocs();
  }

  function renderEditableDocs() {
    if (coverEdit) coverEdit.value = state.coverDraft || "";
    if (soqEdit) soqEdit.value = state.soqDraft || "";
  }

  async function exportDocs(format) {
    if (!genOpportunity || !genOpportunity.value) {
      alert("Select an opportunity first.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(genOpportunity.value)}/export?format=${format}`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCSRF(),
        },
        body: JSON.stringify({
          cover_letter: coverEdit ? coverEdit.value : state.coverDraft,
          soq_body: soqEdit ? soqEdit.value : state.soqDraft,
          title: state.extracted?.title || "",
          agency: state.extracted?.agency || "",
        }),
      });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const ext = format === "pdf" ? "pdf" : "docx";
      a.download = `soq.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err);
    } finally {
      setLoading(false);
    }
  }

  async function fetchUploads() {
    if (!genOpportunity) return;
    const oid = (genOpportunity.value || "").trim();
    if (!oid) {
      renderUploads([]);
      return;
    }
    try {
      const res = await fetch(`/uploads/list/${encodeURIComponent(oid)}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load uploads");
      const data = await res.json();
      const rows = Array.isArray(data) ? data : [];
      state.uploads = rows;
      state.selectedUploads = new Set(
        Array.from(state.selectedUploads).filter((id) => rows.some((r) => r.id === id))
      );
      renderUploads(rows);
    } catch (err) {
      console.error(err);
      renderUploads([]);
    }
  }

  function renderUploads(rows) {
    if (!uploadsList) return;
    if (!rows.length) {
      uploadsList.innerHTML = `<div class="empty">No uploads found for this opportunity.</div>`;
      return;
    }
    uploadsList.innerHTML = "";
    rows.forEach((row) => {
      const wrap = document.createElement("div");
      wrap.className = "kb-item";
      const checked = state.selectedUploads.has(row.id) ? "checked" : "";
      wrap.innerHTML = `
        <label class="checkbox">
          <input type="checkbox" data-upload-id="${row.id}" ${checked}>
          <span></span>
        </label>
        <div class="meta">
          <div class="title">${row.filename || "Untitled"}</div>
          <div class="hint">${row.mime || ""} | ${(row.size || 0)} bytes</div>
        </div>
      `;
      uploadsList.appendChild(wrap);
    });
  }

  if (kbListEl) {
    kbListEl.addEventListener("change", (e) => {
      const id = parseInt(e.target.getAttribute("data-id") || "", 10);
      if (!id) return;
      if (e.target.checked) state.selectedDocs.add(id);
      else state.selectedDocs.delete(id);
    });
    kbListEl.addEventListener("click", async (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      const action = btn.getAttribute("data-action");
      const id = parseInt(btn.getAttribute("data-id") || "", 10);
      if (!id) return;
      if (action === "preview") {
        try {
          const res = await fetch(`/api/knowledge/${id}/preview`, { credentials: "include" });
          if (!res.ok) throw new Error("Failed preview");
          const data = await res.json();
          alert((data.extraction_status || "pending") + ":\n\n" + (data.extracted_text || "No text"));
        } catch (err) {
          alert("Preview failed");
        }
      }
      if (action === "extract") {
        try {
          const res = await fetch(`/api/knowledge/${id}/extract`, {
            method: "POST",
            credentials: "include",
            headers: { "X-CSRF-Token": getCSRF() },
          });
          const data = await res.json();
          alert(`Extraction: ${data.extraction_status || "pending"}`);
          fetchDocs();
        } catch (_) {
          alert("Extraction failed");
        }
      }
      if (action === "delete") {
        if (!confirm("Delete this document?")) return;
        try {
          const res = await fetch(`/api/knowledge/${id}`, {
            method: "DELETE",
            credentials: "include",
            headers: { "X-CSRF-Token": getCSRF() },
          });
          if (!res.ok) throw new Error("delete");
          state.selectedDocs.delete(id);
          await fetchDocs();
        } catch (err) {
          alert("Delete failed");
        }
      }
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", fetchDocs);
  }
  fetchTracked();
  if (refreshUploads) {
    refreshUploads.addEventListener("click", fetchUploads);
  }
  if (selectAllDocsBtn) {
    selectAllDocsBtn.addEventListener("click", () => {
      state.docs.forEach((d) => state.selectedDocs.add(d.id));
      renderDocs();
    });
  }
  if (clearDocsBtn) {
    clearDocsBtn.addEventListener("click", () => {
      state.selectedDocs.clear();
      renderDocs();
    });
  }
  if (uploadsList) {
    uploadsList.addEventListener("change", (e) => {
      const id = parseInt(e.target.getAttribute("data-upload-id") || "", 10);
      if (!id) return;
      if (e.target.checked) state.selectedUploads.add(id);
      else state.selectedUploads.delete(id);
    });
  }

  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const files = kbFiles && kbFiles.files ? Array.from(kbFiles.files) : [];
      if (!files.length) {
        alert("Select at least one file.");
        return;
      }
      const fd = new FormData();
      fd.append("doc_type", kbDocType.value || "other");
      fd.append("tags", kbTags.value || "[]");
      files.forEach((f) => fd.append("files", f, f.name));
      setLoading(true);
      try {
        const res = await fetch("/api/knowledge/upload", {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": getCSRF() },
          body: fd,
        });
        if (!res.ok) throw new Error("upload failed");
        kbFiles.value = "";
        await fetchDocs();
      } catch (err) {
        alert("Upload failed");
      } finally {
        setLoading(false);
      }
    });
  }

  function renderSections() {
    if (!sectionsList) return;
    sectionsList.innerHTML = "";
    if (!state.sections.length) {
      sectionsList.innerHTML = `<div class="empty">No sections added yet.</div>`;
      return;
    }
    state.sections.forEach((s) => {
      const row = document.createElement("div");
      row.className = "section-row";
      row.innerHTML = `
        <div>
          <div class="label">${s.question}</div>
          <div class="hint">Max words: ${s.max_words || "-"} | Required: ${s.required ? "Yes" : "No"}</div>
        </div>
        <button class="ghost-btn danger" data-id="${s.id}">Remove</button>
      `;
      row.querySelector("button").addEventListener("click", () => {
        state.sections = state.sections.filter((it) => it.id !== s.id);
        renderSections();
      });
      sectionsList.appendChild(row);
    });
  }

  if (addSectionBtn) {
    addSectionBtn.addEventListener("click", () => {
      const q = (secQuestion.value || "").trim();
      const mw = parseInt(secMaxWords.value || "", 10);
      const required = !!secRequired.checked;
      if (!q) {
        alert("Enter a question.");
        return;
      }
      state.sections.push({
        id: `sec-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        question: q,
        max_words: isNaN(mw) ? null : mw,
        required,
      });
      secQuestion.value = "";
      secMaxWords.value = "";
      secRequired.checked = true;
      renderSections();
    });
  }

  if (genForm) {
    genForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!state.sections.length) {
        alert("Add at least one section.");
        return;
      }
      const payload = {
        opportunity_id: genOpportunity.value || "",
        win_theme_ids: [],
        knowledge_doc_ids: Array.from(state.selectedDocs),
        instruction_upload_ids: Array.from(state.selectedUploads),
        custom_instructions: genInstructions.value || "",
        sections: state.sections.map((s) => ({
          id: s.id,
          question: s.question,
          max_words: s.max_words,
          required: s.required,
        })),
      };
      setLoading(true);
      try {
        const res = await fetch("/api/rfp-responses/generate", {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": getCSRF(),
          },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText || `HTTP ${res.status}`);
        }
        const data = await res.json();
        renderResults(data);
      } catch (err) {
        alert("Generation failed: " + err);
      } finally {
        setLoading(false);
      }
    });
  }

  function renderResults(data) {
    if (!resultsEl) return;
    const sections = data.sections || [];
    if (!sections.length) {
      resultsEl.innerHTML = `<div class="empty">No results yet.</div>`;
      return;
    }
    resultsEl.innerHTML = "";
    sections.forEach((s) => {
      const card = document.createElement("article");
      card.className = "result";
      card.innerHTML = `
        <div class="result-head">
          <div>
            <p class="eyebrow">${s.id || ""}</p>
            <h4>${s.question || ""}</h4>
          </div>
          <div class="meta">
            <span class="pill">${(s.confidence || 0).toFixed(2)} conf</span>
            <span class="pill">${s.word_count || 0} words</span>
          </div>
        </div>
        <div class="result-body">${(s.answer || "").replace(/\\n/g, "<br>")}</div>
        <div class="result-foot">
          <div class="hint">Sources: ${(s.sources || []).join(", ") || "None"}</div>
        </div>
      `;
      resultsEl.appendChild(card);
    });
  }

  if (resultsClear) {
    resultsClear.addEventListener("click", () => {
      resultsEl.innerHTML = `<div class="empty">Cleared.</div>`;
    });
  }

  if (genOpportunity) {
    genOpportunity.addEventListener("change", () => {
      fetchExtraction();
      fetchUploads();
    });
  }
  if (generateDocsBtn) {
    generateDocsBtn.addEventListener("click", generateDocs);
  }
  if (regenSummaryBtn) {
    regenSummaryBtn.addEventListener("click", regenerateSummary);
  }

  // Initial load
  fetchDocs();
  renderSections();
  fetchExtraction();
})(); 
