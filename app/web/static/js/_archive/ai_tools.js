(function () {
  const getCSRF = () => {
    try {
      return (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || "";
    } catch (_) {
      return "";
    }
  };

  const elements = {};
  const ids = [
    "genForm",
    "genOpportunity",
    "genInstructions",
    "uploadsList",
    "refreshUploads",
    "rfpUploadBtn",
    "rfpUploadInput",
    "addSection",
    "sectionsList",
    "secQuestion",
    "secMaxWords",
    "secRequired",
    "results",
    "resultsClear",
    "summaryCard",
    "checklist",
    "instructionsBlock",
    "generateDocs",
    "docsContainer",
    "regenSummary",
    "coverEdit",
    "soqEdit",
    "exportWord",
    "exportPdf",
    "detectQuestions",
    "presenceBar",
    "presenceList",
    "commentsList",
    "commentText",
    "commentSend",
    "sessionPicker",
    "saveIndicator",
    "progressFill",
    "progressSteps",
    "progressDetail",
    "questionList",
    "addQuestionBtn",
    "prevQuestion",
    "nextQuestion",
    "questionNumber",
    "currentQuestion",
    "questionMeta",
    "answerEditor",
    "wordCount",
    "wordLimit",
    "complianceBadge",
    "confidenceFill",
    "confidenceValue",
    "regenerateBtn",
    "approveBtn",
  ];
  ids.forEach((id) => (elements[id] = document.getElementById(id)));

  const {
    genForm,
    genOpportunity,
    genInstructions,
    uploadsList,
    refreshUploads,
    rfpUploadBtn,
    rfpUploadInput,
    addSection: addSectionBtn,
    sectionsList,
    secQuestion,
    secMaxWords,
    secRequired,
    results: resultsEl,
    resultsClear,
    summaryCard,
    checklist: checklistEl,
    instructionsBlock,
    generateDocs: generateDocsBtn,
    docsContainer,
    regenSummary: regenSummaryBtn,
    coverEdit,
    soqEdit,
    exportWord: exportWordBtn,
    exportPdf: exportPdfBtn,
    detectQuestions: detectQuestionsBtn,
    presenceBar,
    presenceList,
    commentsList,
    commentText,
    commentSend,
    sessionPicker,
    saveIndicator,
    progressFill,
    progressSteps,
    progressDetail,
    questionList,
    addQuestionBtn,
    prevQuestion,
    nextQuestion,
    questionNumber,
    currentQuestion,
    questionMeta,
    answerEditor,
    wordCount,
    wordLimit,
    complianceBadge,
    confidenceFill,
    confidenceValue,
    regenerateBtn,
    approveBtn,
    previewPanel,
    previewContent,
    closePreview,
    previewExport,
    previewEdit,
  } = elements;

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
    activeSectionIndex: 0,
  };
  let wsLoaded = false;
  const pendingRequests = new Map();
  let currentSessionId = null;
  const AUTOSAVE_INTERVAL = 30000;
  let autosaveTimer = null;
  let typingLock = false;

  function setComponentLoading(elementId, loading) {
    const el = elements[elementId];
    if (!el) return;
    if (loading) {
      el.classList.add("loading");
      if (!el.querySelector(".inline-spinner")) {
        el.insertAdjacentHTML("beforeend", '<div class="inline-spinner"></div>');
      }
    } else {
      el.classList.remove("loading");
      const sp = el.querySelector(".inline-spinner");
      if (sp) sp.remove();
    }
  }

  async function fetchWithDedup(url, options = {}) {
    const key = `${options.method || "GET"}:${url}`;
    if (pendingRequests.has(key)) {
      return pendingRequests.get(key);
    }
    const p = fetch(url, { credentials: "include", ...options })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .finally(() => pendingRequests.delete(key));
    pendingRequests.set(key, p);
    return p;
  }

  function ensureCollabLoaded() {
    if (wsLoaded) return;
    wsLoaded = true;
  }

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
    setComponentLoading("summaryCard", true);
    try {
      const data = await fetchWithDedup(
        `/api/opportunities/${encodeURIComponent(genOpportunity.value)}/extracted`
      );
      state.extracted = data;
    } catch (err) {
      console.error(err);
      state.extracted = null;
    } finally {
      setComponentLoading("summaryCard", false);
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
    updateProgress();
  }

  async function generateDocs() {
    if (!genOpportunity || !genOpportunity.value) {
      alert("Select an opportunity first.");
      return;
    }
    setComponentLoading("docsContainer", true);
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
      if (previewPanel && previewContent) {
        previewContent.innerHTML = `<pre>${JSON.stringify(data.documents || {}, null, 2)}</pre>`;
      }
    } catch (err) {
      alert("Generation failed: " + err);
    } finally {
      setComponentLoading("docsContainer", false);
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
    setComponentLoading("summaryCard", true);
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
      setComponentLoading("summaryCard", false);
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
    if (previewPanel && previewContent) {
      // default to cover letter
      previewContent.innerHTML = `<h4>Cover Letter</h4><p>${(cover || "").replace(/\n/g, "<br>")}</p>`;
    }
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

  function debounce(fn, ms) {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => fn(...args), ms);
    };
  }

  function typewriterEffect(el, text, speed = 15) {
    if (!el || !text) return;
    typingLock = true;
    el.classList.add("ai-typing");
    let out = "";
    const setter = "value" in el ? (val) => (el.value = val) : (val) => (el.textContent = val);
    setter("");
    let i = 0;
    const step = () => {
      if (i < text.length) {
        out += text.charAt(i);
        setter(out);
        i += 1;
        setTimeout(step, speed);
      } else {
        el.classList.remove("ai-typing");
        typingLock = false;
      }
    };
    step();
  }

function createSectionCard(s) {
  const card = document.createElement("article");
  card.className = "result";
  const debouncedEdit = debounce((id, val) => handleLocalEdit(id, val), 300);
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
    const answerText = s.answer || "";
    if (answerText) {
      ta.value = "";
      typewriterEffect(ta, answerText, 12);
    } else {
      ta.value = "";
    }
    ta.addEventListener("input", (e) => debouncedEdit(s.id, e.target.value));
  }
  return card;
}

  function renderResultsVirtual(sections) {
    const container = resultsEl;
    if (!container) return;
    // Measure a sample card to better estimate height for virtualization
    let itemHeight = 220;
    if (sections.length) {
      const sample = createSectionCard(sections[0]);
      sample.style.visibility = "hidden";
      sample.style.position = "absolute";
      sample.style.top = "-9999px";
      document.body.appendChild(sample);
      const measured = sample.offsetHeight || 0;
      if (measured > 0) itemHeight = measured;
      document.body.removeChild(sample);
    }
    const viewport = container.clientHeight || Math.floor(window.innerHeight * 0.6) || 600;
    const visibleCount = Math.ceil(viewport / itemHeight) + 2;

    container.innerHTML = "";
    container.style.position = "relative";
    container.style.maxHeight = "70vh";
    container.style.overflowY = "auto";

    const list = document.createElement("div");
    list.style.position = "relative";
    list.style.height = `${sections.length * itemHeight}px`;
    container.appendChild(list);

    let scrollTop = 0;
    function renderVisible() {
      const startIdx = Math.floor(scrollTop / itemHeight);
      const endIdx = Math.min(startIdx + visibleCount, sections.length);
      list.innerHTML = "";
      for (let i = startIdx; i < endIdx; i++) {
        const card = createSectionCard(sections[i]);
        card.style.position = "absolute";
        card.style.top = `${i * itemHeight}px`;
        card.style.left = "0";
        card.style.right = "0";
        list.appendChild(card);
      }
    }

    container.addEventListener("scroll", (e) => {
      scrollTop = e.target.scrollTop;
      requestAnimationFrame(renderVisible);
    });

    renderVisible();
  }

  function renderResults(data) {
    if (!resultsEl) return;
    const sections = data.sections || [];
    state.responseId = data.response_id || state.responseId;
    state.latestSections = sections.map((s) => ({ ...s }));
    state.activeSectionIndex = 0;
    if (state.responseId && !wsLoaded) {
      ensureCollabLoaded();
      connectCollab(state.responseId);
    }
    if (!sections.length) {
      resultsEl.innerHTML = `<div class="empty">No results yet.</div>`;
      return;
    }
    if (sections.length > 30) {
      renderResultsVirtual(sections);
      return;
    }
    resultsEl.innerHTML = "";
    sections.forEach((s) => {
      const card = createSectionCard(s);
      resultsEl.appendChild(card);
    });
    updateProgress();
    renderQuestionSidebar();
    renderActiveEditor();
  }

  const debouncedSync = debounce(async (sectionId, content) => {
    if (!state.responseId) return;
    try {
      await fetch(`/api/rfp-responses/${state.responseId}/sections/${sectionId}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCSRF(),
        },
        body: JSON.stringify({ answer: content }),
      });
      state.latestSections = (state.latestSections || []).map((s) =>
        s.id === sectionId ? { ...s, _dirty: false } : s
      );
    } catch (err) {
      console.error("Sync failed:", err);
    }
  }, 1000);

  function handleLocalEdit(sectionId, content) {
    if (typingLock) return;
    state.latestSections = (state.latestSections || []).map((s) =>
      s.id === sectionId ? { ...s, answer: content, _dirty: true } : s
    );
    // Update local word count immediately
    const wc = (content || "").split(/\s+/).filter(Boolean).length;
    const wcEl = resultsEl
      ?.querySelector(`textarea[data-section-id="${sectionId}"]`)
      ?.closest(".result")
      ?.querySelector(".pill:nth-child(2), .pill:last-child");
    if (wcEl) wcEl.textContent = `${wc} words`;

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
    debouncedSync(sectionId, content);
    markDirty();
    renderQuestionSidebar();
  }

  function updateProgress() {
    const total = state.latestSections.length || state.sections.length || 0;
    const completed = (state.latestSections || []).filter(
      (s) => s.answer && s.answer.split(/\s+/).filter(Boolean).length > 20
    ).length;
    const percent = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    if (progressFill) progressFill.style.width = `${percent || 10}%`;
    if (progressDetail) progressDetail.textContent = `${completed} of ${total}`;
    if (progressSteps) {
      progressSteps.querySelectorAll(".step").forEach((step) => {
        const idx = parseInt(step.getAttribute("data-step") || "0", 10);
        if (idx < 3) {
          step.classList.add("completed");
        } else if (idx === 3) {
          step.classList.add("active");
        }
      });
    }
    if (total > 0 && completed === total && !state.successShown) {
      celebrateSuccess();
      state.successShown = true;
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

  function renderQuestionSidebar() {
    if (!questionList) return;
    const sections = state.latestSections || [];
    const total = sections.length;
    const completed = sections.filter((s) => (s.answer || "").trim().split(/\s+/).filter(Boolean).length > 20).length;
    if (questionBadge) {
      questionBadge.textContent = `${completed}/${total} Complete`;
    }
    questionList.innerHTML = "";
    sections.forEach((s, idx) => {
      const item = document.createElement("div");
      item.className = "question-item" + (idx === state.activeSectionIndex ? " active" : "");
      item.setAttribute("draggable", "true");
      const isDone = (s.answer || "").trim().length > 0;
      item.innerHTML = `
        <div class="status-icon">${isDone ? "✓" : idx + 1}</div>
        <div class="question-preview">${s.question || "Question"}</div>
      `;
      item.addEventListener("click", () => {
        state.activeSectionIndex = idx;
        renderActiveEditor();
        renderQuestionSidebar();
      });
      questionList.appendChild(item);
    });
    initDragAndDrop();
  }

  function updateSectionOrder() {
    if (!questionList) return;
    const items = Array.from(questionList.querySelectorAll(".question-item"));
    const newOrder = [];
    items.forEach((item) => {
      const preview = item.querySelector(".question-preview")?.textContent || "";
      const status = item.querySelector(".status-icon")?.textContent || "";
      const match = state.latestSections.find((s) => (s.question || "") === preview || String(status) === String(s.id));
      if (match) newOrder.push(match);
    });
    if (newOrder.length === state.latestSections.length) {
      state.latestSections = newOrder;
      state.sections = newOrder;
      renderResults({ sections: state.latestSections, response_id: state.responseId });
    }
  }

  function initDragAndDrop() {
    if (!questionList) return;
    let draggedItem = null;

    questionList.addEventListener("dragstart", (e) => {
      draggedItem = e.target.closest(".question-item");
      if (draggedItem) {
        draggedItem.classList.add("dragging");
        if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
      }
    });

    questionList.addEventListener("dragend", () => {
      if (draggedItem) {
        draggedItem.classList.remove("dragging");
        draggedItem = null;
        updateSectionOrder();
      }
    });

    questionList.addEventListener("dragover", (e) => {
      e.preventDefault();
      const afterElement = getDragAfterElement(questionList, e.clientY);
      if (draggedItem) {
        if (!afterElement) {
          questionList.appendChild(draggedItem);
        } else {
          questionList.insertBefore(draggedItem, afterElement);
        }
      }
    });
  }

  function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll(".question-item:not(.dragging)")];
    return draggableElements.reduce(
      (closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          return { offset: offset, element: child };
        } else {
          return closest;
        }
      },
      { offset: Number.NEGATIVE_INFINITY }
    ).element;
  }

  function renderActiveEditor() {
    const sections = state.latestSections || [];
    if (!sections.length) return;
    const idx = Math.min(state.activeSectionIndex, sections.length - 1);
    state.activeSectionIndex = idx;
    const section = sections[idx];
    if (questionNumber) questionNumber.textContent = `Question ${idx + 1} of ${sections.length}`;
    if (currentQuestion) currentQuestion.textContent = section.question || "Question";
    if (questionMeta) {
      const meta = [];
      if (section.max_words) meta.push(`📝 Max ${section.max_words} words`);
      if (section.required) meta.push("⚡ Required");
      questionMeta.innerHTML = meta.map((m) => `<span class="meta-item">${m}</span>`).join("");
    }
    if (answerEditor) {
      answerEditor.innerText = section.answer || "";
    }
    const wc = (section.answer || "").split(/\s+/).filter(Boolean).length;
    if (wordCount) wordCount.textContent = wc;
    if (wordLimit) wordLimit.textContent = section.max_words || "∞";
    if (complianceBadge) complianceBadge.textContent = section.required ? "Required" : "Draft";
    if (confidenceFill) confidenceFill.style.width = `${Math.min(100, Math.round((section.confidence || 0) * 100))}%`;
    if (confidenceValue) confidenceValue.textContent = `${Math.round((section.confidence || 0) * 100)}%`;
  }

  function connectCollab(responseId) {
    ensureCollabLoaded();
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

  if (closePreview && previewPanel) {
    closePreview.addEventListener("click", () => previewPanel.classList.remove("open"));
  }
  if (previewExport) {
    previewExport.addEventListener("click", () => {
      exportDocs("pdf");
    });
  }
  if (previewEdit) {
    previewEdit.addEventListener("click", () => {
      previewPanel.classList.remove("open");
    });
  }
  if (successClose && successModal) {
    successClose.addEventListener("click", () => successModal.classList.remove("show"));
  }

  if (answerEditor) {
    answerEditor.addEventListener("input", () => {
      const sections = state.latestSections || [];
      if (!sections.length) return;
      const idx = state.activeSectionIndex || 0;
      const section = sections[idx];
      const text = answerEditor.innerText || "";
      handleLocalEdit(section.id, text);
      const wc = text.split(/\s+/).filter(Boolean).length;
      if (wordCount) wordCount.textContent = wc;
    });
  }
  if (prevQuestion) {
    prevQuestion.addEventListener("click", () => {
      if (state.activeSectionIndex > 0) {
        state.activeSectionIndex -= 1;
        renderActiveEditor();
        renderQuestionSidebar();
      }
    });
  }
  if (nextQuestion) {
    nextQuestion.addEventListener("click", () => {
      if (state.activeSectionIndex < (state.latestSections.length - 1)) {
        state.activeSectionIndex += 1;
        renderActiveEditor();
        renderQuestionSidebar();
      }
    });
  }
  if (regenerateBtn) {
    regenerateBtn.addEventListener("click", () => alert("Regenerate coming soon"));
  }
  if (approveBtn) {
    approveBtn.addEventListener("click", () => alert("Approved"));
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

  // Session persistence helpers
  function getSessionState() {
    return {
      opportunityId: genOpportunity?.value || null,
      selectedUploads: Array.from(state.selectedUploads),
      sections: state.sections,
      latestSections: state.latestSections,
      coverDraft: state.coverDraft,
      soqDraft: state.soqDraft,
      responseId: state.responseId,
      extracted: state.extracted,
      comments: state.comments,
    };
  }

  function restoreSessionState(sessionState) {
    if (!sessionState) return;
    if (sessionState.opportunityId && genOpportunity) {
      genOpportunity.value = sessionState.opportunityId;
    }
    state.selectedUploads = new Set(sessionState.selectedUploads || []);
    state.sections = sessionState.sections || [];
    state.latestSections = sessionState.latestSections || [];
    state.coverDraft = sessionState.coverDraft || "";
    state.soqDraft = sessionState.soqDraft || "";
    state.responseId = sessionState.responseId || null;
    state.extracted = sessionState.extracted || null;
    state.comments = sessionState.comments || [];

    renderSummary();
    renderSections();
    renderUploads(state.uploads);
    renderEditableDocs();
    if (state.latestSections.length) {
      renderResults({ sections: state.latestSections, response_id: state.responseId });
    }
    if (state.responseId) {
      connectCollab(state.responseId);
    }
  }

  async function saveSession(name = null) {
    const sessionState = getSessionState();
    if (!sessionState.opportunityId && !state.sections.length) {
      return;
    }
    try {
      const res = await fetch("/api/ai-sessions/save", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCSRF(),
        },
        body: JSON.stringify({
          session_id: currentSessionId,
          opportunity_id: sessionState.opportunityId,
          name: name,
          state: sessionState,
        }),
      });
      if (!res.ok) throw new Error("Save failed");
      const data = await res.json();
      currentSessionId = data.session_id;
      showSaveIndicator("Saved");
    } catch (err) {
      console.error("Session save error:", err);
      showSaveIndicator("Save failed", true);
    }
  }

  async function loadSession(sessionId) {
    setLoading(true);
    try {
      const res = await fetch(`/api/ai-sessions/${sessionId}`, { credentials: "include" });
      if (!res.ok) throw new Error("Load failed");
      const data = await res.json();
      currentSessionId = data.id;
      await fetchTracked();
      restoreSessionState(data.state);
      if (data.state?.opportunityId) {
        await Promise.all([fetchExtraction(), fetchUploads()]);
      }
      hideSessionPicker();
    } catch (err) {
      alert("Failed to load session: " + err);
    } finally {
      setLoading(false);
    }
  }

  async function fetchRecentSessions() {
    try {
      const res = await fetch("/api/ai-sessions/recent", { credentials: "include" });
      if (!res.ok) return [];
      return await res.json();
    } catch (err) {
      console.error(err);
      return [];
    }
  }

  async function renderSessionPicker() {
    const picker = sessionPicker;
    if (!picker) return;
    const sessions = await fetchRecentSessions();
    if (!sessions.length) {
      picker.innerHTML = `
        <div class="session-picker-empty">
          <p>No previous sessions found.</p>
          <button class="primary-btn" id="startNewSession">Start New Session</button>
        </div>
      `;
      picker.style.display = "block";
      document.getElementById("startNewSession")?.addEventListener("click", hideSessionPicker);
      return;
    }
    picker.innerHTML = `
      <div class="session-picker-header">
        <h3>Recent Sessions</h3>
        <button class="ghost-btn" id="startNewSession">+ New Session</button>
      </div>
      <div class="session-list">
        ${sessions
          .map(
            (s) => `
          <div class="session-card" data-session-id="${s.id}">
            <div class="session-info">
              <div class="session-title">${s.opportunity_title || s.name || "Untitled Session"}</div>
              <div class="session-meta">
                ${s.agency_name ? `<span>${s.agency_name}</span>` : ""}
                <span>${s.sections_completed || 0}/${s.sections_total || 0} sections</span>
                ${s.has_cover_letter ? '<span class="pill success">Cover Letter</span>' : ""}
                ${s.has_soq ? '<span class="pill success">SOQ</span>' : ""}
              </div>
              <div class="session-time">${formatTimeAgo(s.last_accessed_at)}</div>
            </div>
            <div class="session-actions">
              <button class="ghost-btn load-session">Resume</button>
              <button class="ghost-btn danger delete-session">Delete</button>
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    `;
    picker.style.display = "block";
    document.getElementById("startNewSession")?.addEventListener("click", hideSessionPicker);
    picker.querySelectorAll(".load-session").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const card = e.target.closest(".session-card");
        const sessionId = parseInt(card?.dataset.sessionId || "", 10);
        if (sessionId) loadSession(sessionId);
      });
    });
    picker.querySelectorAll(".delete-session").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const card = e.target.closest(".session-card");
        const sessionId = parseInt(card?.dataset.sessionId || "", 10);
        if (!sessionId || !confirm("Delete this session?")) return;
        await fetch(`/api/ai-sessions/${sessionId}`, {
          method: "DELETE",
          credentials: "include",
          headers: { "X-CSRF-Token": getCSRF() },
        });
        card.remove();
      });
    });
  }

  function hideSessionPicker() {
    if (sessionPicker) sessionPicker.style.display = "none";
  }

  function showSaveIndicator(text, isError = false) {
    if (!saveIndicator) return;
    saveIndicator.textContent = text;
    saveIndicator.classList.toggle("error", isError);
    saveIndicator.classList.add("visible");
    setTimeout(() => saveIndicator.classList.remove("visible"), 2000);
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hr ago`;
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString();
  }

  function startAutosave() {
    if (autosaveTimer) clearInterval(autosaveTimer);
    autosaveTimer = setInterval(() => {
      if (state.sections.length || state.coverDraft || state.soqDraft) {
        saveSession();
      }
    }, AUTOSAVE_INTERVAL);
  }

  function markDirty() {
    clearTimeout(window._dirtySaveTimeout);
    window._dirtySaveTimeout = setTimeout(() => saveSession(), 5000);
  }

  function celebrateSuccess() {
    // Simple confetti
    const confetti = document.createElement("div");
    confetti.className = "confetti";
    for (let i = 0; i < 80; i++) {
      const piece = document.createElement("div");
      piece.className = "confetti-piece";
      piece.style.left = `${Math.random() * 100}%`;
      piece.style.background = ["#0f8b5a", "#10b981", "#f59e0b", "#3b82f6"][i % 4];
      piece.style.animationDelay = `${Math.random()}s`;
      confetti.appendChild(piece);
    }
    document.body.appendChild(confetti);
    setTimeout(() => confetti.remove(), 3200);
    if (successModal) {
      successModal.classList.add("show");
    }
  }

  window.addEventListener("beforeunload", () => {
    if (state.sections.length || state.coverDraft || state.soqDraft) {
      const payload = new Blob(
        [
          JSON.stringify({
            session_id: currentSessionId,
            opportunity_id: genOpportunity?.value,
            state: getSessionState(),
          }),
        ],
        { type: "application/json" }
      );
      navigator.sendBeacon("/api/ai-sessions/save", payload);
    }
  });

  if (coverEdit) {
    coverEdit.addEventListener("input", () => markDirty());
  }
  if (soqEdit) {
    soqEdit.addEventListener("input", () => markDirty());
  }

  async function initSessions() {
    const urlParams = new URLSearchParams(window.location.search);
    const sessionIdParam = urlParams.get("session");
    await fetchTracked();
    renderSections();
    if (sessionIdParam) {
      await loadSession(parseInt(sessionIdParam, 10));
    } else {
      await renderSessionPicker();
      await fetchExtraction();
      await fetchUploads();
    }
    startAutosave();
    if (previewPanel) {
      previewPanel.classList.add("open");
    }
  }

  // Initial load with session support
  initSessions();
})();
