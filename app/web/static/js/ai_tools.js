(function () {
  const getCSRF = () => {
    try {
      return (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || "";
    } catch (_) {
      return "";
    }
  };

  const genForm = document.getElementById("genForm");
  const genOpportunity = document.getElementById("genOpportunity");
  const genInstructions = document.getElementById("genInstructions");
  const uploadsList = document.getElementById("uploadsList");
  const refreshUploads = document.getElementById("refreshUploads");
  const rfpUploadBtn = document.getElementById("rfpUploadBtn");
  const rfpUploadInput = document.getElementById("rfpUploadInput");
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
  const detectQuestionsBtn = document.getElementById("detectQuestions");
  const presenceBar = document.getElementById("presenceBar");
  const presenceList = document.getElementById("presenceList");
  const commentsList = document.getElementById("commentsList");
  const commentText = document.getElementById("commentText");
  const commentSend = document.getElementById("commentSend");

  const overlay = document.createElement("div");
  overlay.className = "loading-overlay";
  overlay.innerHTML = `<div class="spinner"></div><div class="loading-text">Working...</div>`;
  document.body.appendChild(overlay);

  const state = {
    uploads: [],
    selectedUploads: new Set(),
    sections: [],
    loading: false,
    extracted: null,
    coverDraft: "",
    soqDraft: "",
    responseId: null,
    ws: null,
    presence: [],
    comments: [],
    latestSections: [],
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

  async function fetchTracked() {
    if (!genOpportunity) return;
    try {
      const res = await fetch("/api/tracked/my", { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load tracked");
      const data = await res.json();
      genOpportunity.innerHTML = `<option value="">Select a tracked solicitation</option>`;
      (Array.isArray(data) ? data : []).forEach((row) => {
        const opt = document.createElement("option");
        opt.value = row.id;
        const due = row.due_date ? ` | due ${row.due_date}` : "";
        const agency = row.agency_name ? ` | ${row.agency_name}` : "";
        opt.textContent = `${row.title || row.id}${agency}${due}`;
        genOpportunity.appendChild(opt);
      });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchExtraction() {
    if (!genOpportunity || !genOpportunity.value) {
      state.extracted = null;
      renderSummary();
      return;
    }
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(genOpportunity.value)}/extracted`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed extraction fetch");
      const data = await res.json();
      state.extracted = data;
    } catch (err) {
      console.error(err);
      state.extracted = null;
    }
    renderSummary();
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
      const uploadIds = Array.from(state.selectedUploads);
      for (const uid of uploadIds) {
        await fetch(`/api/rfp-extract/${uid}`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": getCSRF() },
        });
      }
      await fetchExtraction();

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
    const cover = docs?.cover_letter || "";
    const soq = docs?.soq || {};
    const checklist = docs?.submission_checklist || docs?.checklist || [];
    const events = docs?.calendar_events || [];

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

    docsContainer.classList.remove("empty");
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
      if (!state.selectedUploads.size && rows.length) {
        state.selectedUploads = new Set([rows[0].id]);
      } else {
        state.selectedUploads = new Set(Array.from(state.selectedUploads).filter((id) => rows.some((r) => r.id === id)));
      }
      renderUploads(rows);
    } catch (err) {
      console.error(err);
      renderUploads([]);
    }
  }

  async function uploadRfp(files) {
    const oid = genOpportunity && genOpportunity.value;
    if (!oid) {
      alert("Select an opportunity first.");
      return;
    }
    if (!files || !files.length) return;
    const fd = new FormData();
    fd.append("opportunity_id", oid);
    Array.from(files).forEach((f) => fd.append("files", f, f.name));
    setLoading(true);
    try {
      const res = await fetch("/uploads/add", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": getCSRF() },
        body: fd,
      });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      await fetchUploads();
    } catch (err) {
      alert("Upload failed: " + err);
    } finally {
      setLoading(false);
      if (rfpUploadInput) rfpUploadInput.value = "";
    }
  }

  async function detectQuestions() {
    if (!genOpportunity || !genOpportunity.value) {
      alert("Select an opportunity first.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(genOpportunity.value)}/detect-questions`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to detect questions");
      const data = await res.json();
      const qs = (data.questions || []).map((q, idx) => ({
        id: q.id || `q-${Date.now()}-${idx}`,
        question: q.text || q.question || "",
        max_words: q.word_limit || q.page_limit || null,
        required: true,
      }));
      state.sections = qs;
      renderSections();
    } catch (err) {
      alert("Detect failed: " + err);
    } finally {
      setLoading(false);
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

  function renderResults(data) {
    if (!resultsEl) return;
    const sections = data.sections || [];
    state.responseId = data.response_id || state.responseId;
    state.latestSections = sections.map((s) => ({ ...s }));
    if (state.responseId) {
      connectCollab(state.responseId);
    }
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
        <div class="result-body">
          <textarea data-section-id="${s.id || ""}" class="result-edit" rows="6" style="width:100%;">${s.answer || ""}</textarea>
        </div>
        <div class="result-foot">
          <div class="hint">Sources: ${(s.sources || []).join(", ") || "None"}</div>
        </div>
      `;
      const ta = card.querySelector("textarea");
      if (ta) {
        ta.addEventListener("input", (e) => handleLocalEdit(s.id, e.target.value));
      }
      resultsEl.appendChild(card);
    });
  }

  function handleLocalEdit(sectionId, content) {
    state.latestSections = (state.latestSections || []).map((s) =>
      s.id === sectionId ? { ...s, answer: content } : s
    );
    if (state.ws && state.ws.readyState === WebSocket.OPEN && state.responseId) {
      state.ws.send(
        JSON.stringify({
          type: "edit",
          section_id: sectionId,
          content,
          cursor: null,
        })
      );
    }
  }

  function applyRemoteEdit(sectionId, content, userEmail) {
    state.latestSections = (state.latestSections || []).map((s) =>
      s.id === sectionId ? { ...s, answer: content } : s
    );
    const ta = resultsEl?.querySelector(`textarea[data-section-id="${sectionId}"]`);
    if (ta && ta !== document.activeElement) {
      ta.value = content || "";
      const note = document.createElement("div");
      note.className = "hint";
      note.textContent = `Updated by ${userEmail}`;
      ta.parentElement?.appendChild(note);
      setTimeout(() => note.remove(), 2000);
    }
  }

  function renderPresence() {
    if (!presenceBar || !presenceList) return;
    if (!state.presence || !state.presence.length) {
      presenceBar.style.display = "none";
      return;
    }
    presenceBar.style.display = "inline-flex";
    presenceList.textContent = state.presence.join(", ");
  }

  function renderComments() {
    if (!commentsList) return;
    const list = state.comments || [];
    if (!list.length) {
      commentsList.innerHTML = `<div class="empty">No comments yet.</div>`;
      return;
    }
    commentsList.innerHTML = "";
    list.forEach((c) => {
      const row = document.createElement("div");
      row.className = "comment-row";
      row.innerHTML = `<strong>${c.user || "User"}:</strong> ${c.content || ""} ${c.section_id ? `(Section ${c.section_id})` : ""}`;
      commentsList.appendChild(row);
    });
  }

  function connectCollab(responseId) {
    if (!responseId || typeof WebSocket === "undefined") return;
    if (state.ws) {
      try {
        state.ws.close();
      } catch (_) {}
    }
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/response/${responseId}`);
    state.ws = ws;
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === "presence") {
          state.presence = msg.users || [];
          renderPresence();
        } else if (msg.type === "edit") {
          applyRemoteEdit(msg.section_id, msg.content, msg.user);
        } else if (msg.type === "comment") {
          state.comments = [...(state.comments || []), msg];
          renderComments();
        } else if (msg.type === "init") {
          state.comments = msg.comments || [];
          state.presence = msg.presence || [];
          renderPresence();
          renderComments();
        }
      } catch (err) {
        console.error("WS message error", err);
      }
    };
    ws.onclose = () => {
      state.ws = null;
    };
  }

  if (resultsClear) {
    resultsClear.addEventListener("click", () => {
      resultsEl.innerHTML = `<div class="empty">Cleared.</div>`;
    });
  }
  if (commentSend) {
    commentSend.addEventListener("click", () => {
      const text = (commentText?.value || "").trim();
      if (!text || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
        if (!text) alert("Enter a comment first.");
        return;
      }
      state.ws.send(
        JSON.stringify({
          type: "comment",
          content: text,
          section_id: null,
          created_at: new Date().toISOString(),
        })
      );
      commentText.value = "";
    });
  }

  if (genOpportunity) {
    genOpportunity.addEventListener("change", () => {
      fetchExtraction();
      fetchUploads();
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
  if (refreshUploads) {
    refreshUploads.addEventListener("click", fetchUploads);
  }
  if (rfpUploadBtn && rfpUploadInput) {
    rfpUploadBtn.addEventListener("click", () => rfpUploadInput.click());
    rfpUploadInput.addEventListener("change", () => uploadRfp(rfpUploadInput.files));
  }
  if (detectQuestionsBtn) {
    detectQuestionsBtn.addEventListener("click", detectQuestions);
  }
  if (generateDocsBtn) {
    generateDocsBtn.addEventListener("click", generateDocs);
  }
  if (regenSummaryBtn) {
    regenSummaryBtn.addEventListener("click", regenerateSummary);
  }
  if (exportWordBtn) {
    exportWordBtn.addEventListener("click", () => exportDocs("docx"));
  }
  if (exportPdfBtn) {
    exportPdfBtn.addEventListener("click", () => exportDocs("pdf"));
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
        knowledge_doc_ids: [],
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

  // Initial load
  fetchTracked();
  renderSections();
  fetchExtraction();
})();
