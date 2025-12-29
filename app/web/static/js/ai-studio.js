(function () {
  const getCsrf = () => {
    const hiddenToken = document.getElementById("csrfTokenField")?.value;
    if (hiddenToken) return hiddenToken;
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (!match || !match[1]) {
      throw new Error("Missing CSRF token. Please reload and try again.");
    }
    return match[1];
  };

  const els = {
    progressFill: document.getElementById("progressFill"),
    progressText: document.getElementById("progressText"),
    progressPercent: document.getElementById("progressPercent"),
    genOpportunity: document.getElementById("genOpportunity"),
    uploadArea: document.getElementById("uploadArea"),
    rfpUploadInput: document.getElementById("rfpUploadInput"),
    uploadedFile: document.getElementById("uploadedFile"),
    fileName: document.getElementById("fileName"),
    fileSize: document.getElementById("fileSize"),
    removeFile: document.getElementById("removeFile"),
    step1Next: document.getElementById("step1Next"),
    step2Next: document.getElementById("step2Next"),
    step2Back: document.getElementById("step2Back"),
    step3Next: document.getElementById("step3Next"),
    step3Back: document.getElementById("step3Back"),
    step4Back: document.getElementById("step4Back"),
    extractBtn: document.getElementById("extractBtn"),
    extractResults: document.getElementById("extractResults"),
    summaryText: document.getElementById("summaryText"),
    checklistItems: document.getElementById("checklistItems"),
    keyDates: document.getElementById("keyDates"),
    extractStatus: document.getElementById("extractStatus"),
    generateBtn: document.getElementById("generateBtn"),
    generateError: document.getElementById("generateError"),
    generateOptions: document.getElementById("generateOptions"),
    customInstructions: document.getElementById("customInstructions"),
    documentEditor: document.getElementById("documentEditor"),
    editableContent: document.getElementById("editableContent"),
    previewContent: document.getElementById("previewContent"),
    wordCount: document.getElementById("wordCount"),
    saveIndicator: document.getElementById("saveIndicator"),
    exportWord: document.getElementById("exportWord"),
    exportPdf: document.getElementById("exportPdf"),
    completionMessage: document.getElementById("completionMessage"),
    startNew: document.getElementById("startNew"),
    statusMessage: document.getElementById("statusMessage"),
    reviewOpportunity: document.getElementById("reviewOpportunity"),
    resumeLatest: document.getElementById("resumeLatest"),
    manualSave: document.getElementById("manualSave"),
    manualSaveInline: document.getElementById("manualSaveInline"),
    improveBtn: document.getElementById("improveBtn"),
    shortenBtn: document.getElementById("shortenBtn"),
    expandBtn: document.getElementById("expandBtn"),
    tabNavLeft: document.querySelector(".tab-nav-left"),
    tabNavRight: document.querySelector(".tab-nav-right"),
    fullscreenBtn: document.querySelector(".tab-action"),
    existingDocsList: document.getElementById("existingDocsList"),
    existingDocPane: document.getElementById("existingDocPane"),
    uploadDocPane: document.getElementById("uploadDocPane"),
    uploadProgress: document.getElementById("uploadProgress"),
    uploadProgressBar: document.getElementById("uploadProgressBar"),
    uploadProgressFill: document.getElementById("uploadProgressFill"),
    editorTabs: document.querySelectorAll(".editor-tab"),
    toolbarBtns: document.querySelectorAll(".toolbar-btn"),
    optionCards: document.querySelectorAll(".generate-option"),
    docTabButtons: document.querySelectorAll(".doc-tab"),
    sessionModalOverlay: document.getElementById("sessionModalOverlay"),
    sessionModal: document.getElementById("sessionModal"),
    sessionList: document.getElementById("sessionList"),
    sessionCount: document.getElementById("sessionCount"),
    sessionSelectionCount: document.getElementById("sessionSelectionCount"),
    sessionSelectAll: document.getElementById("sessionSelectAll"),
    bulkDeleteSessions: document.getElementById("bulkDeleteSessions"),
    openSessionPicker: document.getElementById("openSessionPicker"),
    closeSessionModal: document.getElementById("closeSessionModal"),
    newSessionBtn: document.getElementById("newSessionBtn"),
    currentSessionName: document.getElementById("currentSessionName"),
    currentSessionTime: document.getElementById("currentSessionTime"),
    openSessionPickerTop: document.getElementById("openSessionPickerTop"),
  };

  const steps = {
    1: document.getElementById("step1"),
    2: document.getElementById("step2"),
    3: document.getElementById("step3"),
    4: document.getElementById("step4"),
  };

  const state = {
    currentStep: 1,
    opportunityId: "",
    opportunityLabel: "",
    upload: null,
    extracted: null,
    documents: {},
    responseSections: [],
    currentDoc: "cover",
    sessionId: null,
    existingDocs: [],
    sectionDocs: {},
    allowAugment: false,
    isExtracting: false,
  };
  window.aiStudioState = state;

  let saveTimer = null;
  let augmentingExtraction = false;
  let saveInFlight = false;
  let saveQueued = false;
  let queuedManualSave = false;
  let previewPageIndex = 0;
  const MAX_UPLOAD_MB = 25;
  const allowedTypes = [".pdf", ".doc", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".gif", ".webp"];

  function sanitizeHtml(html) {
    if (!html) return "";
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    doc.querySelectorAll("script, style").forEach((n) => n.remove());
    doc.querySelectorAll("*").forEach((el) => {
      [...el.attributes].forEach((attr) => {
        const name = attr.name.toLowerCase();
        if (name.startsWith("on") || name === "srcdoc") {
          el.removeAttribute(attr.name);
        }
      });
    });
    return doc.body.innerHTML || "";
  }

  function setButtonLoading(btn, text) {
    if (!btn) return;
    if (!btn.dataset.originalText) {
      btn.dataset.originalText = btn.innerHTML;
    }
    if (text) {
      btn.innerHTML = `<span class="spinner spin"></span><span>${text}</span>`;
      btn.classList.add("btn-loading");
      btn.disabled = true;
    } else {
      btn.innerHTML = btn.dataset.originalText;
      btn.classList.remove("btn-loading");
      btn.disabled = false;
    }
  }

  function showMessage(msg, type = "info") {
    if (!els.statusMessage) return;
    els.statusMessage.textContent = msg || "";
    els.statusMessage.classList.remove("hidden", "error", "success");
    if (type === "error") {
      els.statusMessage.classList.add("error");
    } else if (type === "success") {
      els.statusMessage.classList.add("success");
    }
  }

  function clearMessage() {
    if (els.statusMessage) {
      els.statusMessage.classList.add("hidden");
    }
    if (els.extractStatus) {
      els.extractStatus.classList.add("hidden");
      els.extractStatus.textContent = "";
    }
  }

  function showSaveIndicator(text, isError = false) {
    if (!els.saveIndicator) return;
    els.saveIndicator.textContent = text;
    els.saveIndicator.classList.toggle("error", isError);
    els.saveIndicator.classList.remove("hidden");
    setTimeout(() => els.saveIndicator.classList.add("hidden"), 2000);
  }

  function updateProgress() {
    const percent = ((state.currentStep - 1) / 3) * 100;
    if (els.progressFill) els.progressFill.style.width = `${percent}%`;
    if (els.progressText) els.progressText.textContent = `Step ${state.currentStep} of 4`;
    if (els.progressPercent) els.progressPercent.textContent = `${Math.round(percent)}% complete`;
  }

  function goToStep(step) {
    Object.entries(steps).forEach(([idx, el]) => {
      const n = Number(idx);
      el?.classList.remove("active", "completed");
      if (n < step) {
        el?.classList.add("completed");
      } else if (n === step) {
        el?.classList.add("active");
      }
    });
    state.currentStep = step;
    updateProgress();
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 MB";
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function validateFile(file) {
    if (!file) return false;
    const ext = (file.name || "").toLowerCase();
    const allowed = allowedTypes.some((t) => ext.endsWith(t));
    if (!allowed) {
      showMessage(`Unsupported file type. Allowed: ${allowedTypes.join(", ")}`, "error");
      return false;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      showMessage(`File too large. Max ${MAX_UPLOAD_MB} MB.`, "error");
      return false;
    }
    return true;
  }

  function normalizeId(val) {
    return val == null ? "" : String(val);
  }

  function formatDate(dateStr) {
    if (!dateStr) return "Unknown date";
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function handleStepAvailability() {
    if (els.step1Next) {
      els.step1Next.disabled = !(state.opportunityId && state.upload);
    }
    if (els.extractBtn) {
      els.extractBtn.disabled = !state.upload;
    }
    if (els.step2Next) {
      els.step2Next.disabled = !state.extracted;
    }
    if (els.generateBtn) {
      els.generateBtn.disabled = !state.extracted;
    }
    if (els.step3Next) {
      const hasContent = Object.values(state.documents || {}).some(
        (content) => typeof content === "string" && content.trim().length > 0
      );
      els.step3Next.disabled = !hasContent;
    }
  }

  function switchDocTab(tab) {
    const target = tab === "upload" ? "upload" : "existing";
    els.docTabButtons.forEach((btn) => {
      const isActive = btn.dataset.tab === target;
      btn.classList.toggle("active", isActive);
      if (btn.hasAttribute("aria-selected")) {
        btn.setAttribute("aria-selected", isActive ? "true" : "false");
      }
    });
    if (els.existingDocPane) {
      els.existingDocPane.classList.toggle("active", target === "existing");
    }
    if (els.uploadDocPane) {
      els.uploadDocPane.classList.toggle("active", target === "upload");
    }
  }

  function renderExistingDocuments(selectedId = null) {
    if (!els.existingDocsList) return;
    const docs = state.existingDocs || [];
    const activeId = selectedId || (state.upload && state.upload.id);
    if (!docs.length) {
      els.existingDocsList.innerHTML = `<div class="doc-empty">No documents uploaded yet for this opportunity.</div>`;
      return;
    }
    els.existingDocsList.innerHTML = "";
    docs.forEach((doc) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const isSelected = String(activeId ?? "") === String(doc.id ?? "");
      btn.className = `doc-card${isSelected ? " selected" : ""}`;
      btn.dataset.uploadId = doc.id;
      btn.innerHTML = `
        <div class="doc-icon">&#128462;</div>
        <div class="doc-meta">
          <div class="doc-name">${doc.filename || "Untitled"}</div>
          <div class="doc-details">${formatBytes(doc.size)} &bull; Uploaded ${formatDate(doc.created_at)}</div>
        </div>
        <div class="doc-arrow">&#10140;</div>
      `;
      els.existingDocsList.appendChild(btn);
    });
  }

  function ensureSectionDocs(sectionKey) {
    if (!state.sectionDocs) state.sectionDocs = {};
    if (!state.sectionDocs[sectionKey]) state.sectionDocs[sectionKey] = [];
    return state.sectionDocs[sectionKey];
  }

  function renderSectionChips(sectionKey) {
    const container = els.generateOptions?.querySelector(`.support-chips[data-section="${sectionKey}"]`);
    if (!container) return;
    const docs = ensureSectionDocs(sectionKey);
    if (!docs.length) {
      container.innerHTML = `<span class="chip empty">No docs</span>`;
      return;
    }
    container.innerHTML = "";
    docs.forEach((doc) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.dataset.docId = normalizeId(doc.id);
      chip.dataset.section = sectionKey;
      chip.innerHTML = `${escapeHtml(doc.filename || "Doc")} <button type="button" class="chip-remove" aria-label="Remove">&times;</button>`;
      container.appendChild(chip);
    });
  }

  function removeDocFromSection(sectionKey, docId) {
    const docs = ensureSectionDocs(sectionKey);
    const key = normalizeId(docId);
    const next = docs.filter((d) => normalizeId(d.id) !== key);
    state.sectionDocs[sectionKey] = next;
    renderSectionChips(sectionKey);
    scheduleSave();
  }

  function selectExistingDocument(doc) {
    if (!doc) return;
    state.upload = doc;
    state.extracted = null;
    if (els.extractResults) {
      els.extractResults.classList.add("hidden");
    }
    renderUpload(doc);
    renderExistingDocuments(doc.id);
    handleStepAvailability();
    showMessage(`Selected ${doc.filename || "document"}. Run extraction to continue.`, "success");
    scheduleSave();
  }

  async function fetchExistingDocuments(opportunityId = state.opportunityId, preselectId = null) {
    if (!opportunityId || !els.existingDocsList) return [];
    els.existingDocsList.innerHTML = `<div class="doc-empty">Loading documents...</div>`;
    try {
      const res = await fetch(`/uploads/list/${encodeURIComponent(opportunityId)}`, {
        credentials: "include",
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Unable to load documents (${res.status})`);
      }
      const data = await res.json();
      state.existingDocs = Array.isArray(data) ? data : [];
      const selectedId =
        preselectId ||
        (state.upload && state.upload.id) ||
        (state.existingDocs.length === 1 ? state.existingDocs[0].id : null);
      const selectedDoc = state.existingDocs.find((d) => String(d.id) === String(selectedId));
      if (selectedDoc) {
        state.upload = selectedDoc;
        renderUpload(selectedDoc);
      } else if (state.opportunityId === opportunityId) {
        state.upload = null;
        if (els.uploadedFile) els.uploadedFile.classList.add("hidden");
        if (els.uploadArea) els.uploadArea.style.display = "block";
      }
      renderExistingDocuments(selectedDoc ? selectedDoc.id : null);
      handleStepAvailability();
      return state.existingDocs;
    } catch (err) {
      els.existingDocsList.innerHTML = `<div class="doc-empty error">${err.message || "Could not load documents."}</div>`;
      handleStepAvailability();
      return [];
    }
  }

  function getExtractedObject(root) {
    if (!root) return {};
    return (
      (root.extracted && (root.extracted.extracted || root.extracted.discovery || root.extracted)) ||
      root.discovery ||
      root ||
      {}
    );
  }

  function normalizeDates(extracted, root) {
    const raw =
      extracted.key_dates ||
      extracted.timeline ||
      extracted.deadlines ||
      (root && root.discovery && (root.discovery.key_dates || root.discovery.timeline || root.discovery.deadlines)) ||
      [];
    if (!Array.isArray(raw)) return [];
    return raw
      .map((d) => {
        if (!d) return null;
        if (typeof d === "string") {
          return { title: d, due_date: "" };
        }
        const title = d.title || d.event || d.name || "";
        const due = d.due_date || d.date || "";
        const time = d.time ? ` ${d.time}` : "";
        const tz = d.timezone ? ` ${d.timezone}` : "";
        return { title, due_date: `${due}${time}${tz}`.trim() };
      })
      .filter(Boolean);
  }

  function hasExtractionContent(root) {
    const extracted = getExtractedObject(root);
    if (!extracted || !Object.keys(extracted).length) return false;
    const summary =
      extracted.summary ||
      extracted.scope_of_work ||
      (root && root.discovery && root.discovery.summary) ||
      (root && root.summary) ||
      "";
    const checklist = []
      .concat(extracted.required_documents || [])
      .concat(extracted.required_forms || [])
      .concat(extracted.checklist || [])
      .concat(extracted.compliance_terms || [])
      .concat((root && root.discovery && root.discovery.requirements) || [])
      .filter(Boolean);
    const dates = normalizeDates(extracted, root);
    return Boolean((summary && summary.trim()) || (checklist && checklist.length) || (dates && dates.length));
  }

  async function fetchTrackedOpportunities() {
    const select = els.genOpportunity;
    if (!select) return;
    select.innerHTML = `<option value="">Loading tracked opportunities...</option>`;
    try {
      const res = await fetch("/api/tracked/my", {
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `Unable to load tracked (${res.status})`);
      }
      const data = await res.json();
      select.innerHTML = `<option value="">Select a tracked solicitation</option>`;
      (Array.isArray(data) ? data : []).forEach((row) => {
        const option = document.createElement("option");
        option.value = row.id;
        const due = row.due_date ? ` - Due ${row.due_date}` : "";
        const agency = row.agency_name ? ` - ${row.agency_name}` : "";
        option.textContent = `${row.title || "Untitled"}${agency}${due}`;
        select.appendChild(option);
      });
      if (state.opportunityId) {
        select.value = state.opportunityId;
      }
    } catch (err) {
      showMessage(err.message || "Could not load tracked opportunities. Try refreshing.", "error");
      if (state.opportunityLabel && state.opportunityId) {
        select.innerHTML = `<option value="${state.opportunityId}">${state.opportunityLabel}</option>`;
      } else {
        select.innerHTML = `<option value="">Unable to load tracked opportunities</option>`;
      }
    }
  }

  async function uploadFile(file) {
    if (!state.opportunityId) {
      showMessage("Select an opportunity before uploading.", "error");
      return null;
    }
    if (!file) return null;
    const ext = (file.name || "").toLowerCase();
    const allowed = allowedTypes.some((t) => ext.endsWith(t));
    if (!allowed) {
      showMessage(`Unsupported file type. Allowed: ${allowedTypes.join(", ")}`, "error");
      return null;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      showMessage(`File too large. Max ${MAX_UPLOAD_MB} MB.`, "error");
      return null;
    }
    const fd = new FormData();
    fd.append("opportunity_id", state.opportunityId);
    fd.append("folder_type", "ai-studio");
    fd.append("files", file, file.name);
    const xhr = new XMLHttpRequest();
    try {
      setButtonLoading(els.step1Next, null);
      showMessage("Uploading file...", "info");
      if (els.uploadProgress) {
        els.uploadProgress.classList.remove("hidden");
      }
      xhr.upload.onprogress = (evt) => {
        if (!evt.lengthComputable) return;
        const pct = Math.round((evt.loaded / evt.total) * 100);
        if (els.uploadProgressBar) {
          els.uploadProgressBar.textContent = `Uploading... ${pct}%`;
        }
        if (els.uploadProgressFill) {
          els.uploadProgressFill.style.width = `${pct}%`;
        }
      };
      const res = await new Promise((resolve, reject) => {
        xhr.onreadystatechange = () => {
          if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch (err) {
                reject(err);
              }
            } else {
              reject(new Error(xhr.responseText || `Upload failed (${xhr.status})`));
            }
          }
        };
        xhr.open("POST", "/uploads/add", true);
        xhr.withCredentials = true;
        try {
          xhr.setRequestHeader("X-CSRF-Token", getCsrf());
        } catch (err) {
          // CSRF error is surfaced when sending
        }
        xhr.send(fd);
      });
      const uploaded = res.files?.[0];
      if (!uploaded) throw new Error("Upload failed. No file returned.");
      state.upload = uploaded;
      state.extracted = null;
      if (els.extractResults) {
        els.extractResults.classList.add("hidden");
      }
      renderUpload(uploaded, file);
      await fetchExistingDocuments(state.opportunityId, uploaded.id);
      handleStepAvailability();
      showMessage("Upload successful. Ready to extract.", "success");
      scheduleSave();
      return uploaded;
    } catch (err) {
      showMessage(err.message || "Upload failed.", "error");
      return null;
    } finally {
      if (els.uploadProgressBar) {
        els.uploadProgressBar.textContent = "";
      }
      if (els.uploadProgressFill) {
        els.uploadProgressFill.style.width = "0%";
      }
      if (els.uploadProgress) {
        els.uploadProgress.classList.add("hidden");
      }
      handleStepAvailability();
    }
    try {
      setButtonLoading(els.step1Next, null);
      showMessage("Uploading file...", "info");
      const res = await fetch("/uploads/add", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed (${res.status})`);
      }
      const data = await res.json();
      const uploaded = data.files?.[0];
      if (!uploaded) throw new Error("Upload failed. No file returned.");
      state.upload = uploaded;
      state.extracted = null;
      if (els.extractResults) {
        els.extractResults.classList.add("hidden");
      }
      renderUpload(uploaded, file);
      await fetchExistingDocuments(state.opportunityId, uploaded.id);
      handleStepAvailability();
      showMessage("Upload successful. Ready to extract.", "success");
      scheduleSave();
      return uploaded;
    } catch (err) {
      showMessage(err.message || "Upload failed.", "error");
      return null;
    } finally {
      handleStepAvailability();
    }
  }

  function renderUpload(uploaded, file) {
    if (!els.uploadedFile || !els.uploadArea) return;
    const name = uploaded?.filename || file?.name || "";
    els.fileName && (els.fileName.textContent = name);
    const size = uploaded?.size || file?.size;
    els.fileSize && (els.fileSize.textContent = formatBytes(size));
    els.uploadedFile.classList.remove("hidden");
    els.uploadArea.style.display = "none";
  }

  async function uploadSectionFiles(sectionKey, files) {
    if (!state.opportunityId) {
      showMessage("Select an opportunity before uploading.", "error");
      return;
    }
    const list = Array.from(files || []).filter(Boolean);
    const valid = list.filter((f) => validateFile(f));
    if (!valid.length) return;
    const fd = new FormData();
    fd.append("opportunity_id", state.opportunityId);
    fd.append("folder_type", "ai-studio-output");
    valid.forEach((f) => fd.append("files", f, f.name));
    try {
      showMessage(`Uploading docs for ${sectionKey.replace(/_/g, " ") || "section"}...`, "info");
      const res = await fetch("/uploads/add", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed (${res.status})`);
      }
      const data = await res.json();
      const uploaded = (data.files || []).map((f) => ({
        ...f,
        created_at: f.created_at || new Date().toISOString(),
      }));

      // merge into existing docs map
      const map = new Map((state.existingDocs || []).map((d) => [normalizeId(d.id), d]));
      uploaded.forEach((u) => map.set(normalizeId(u.id), { ...map.get(normalizeId(u.id)), ...u }));
      state.existingDocs = Array.from(map.values());

      const docs = ensureSectionDocs(sectionKey);
      uploaded.forEach((u) => {
        const key = normalizeId(u.id);
        if (!docs.find((d) => normalizeId(d.id) === key)) {
          docs.push(u);
        }
      });
      renderSectionChips(sectionKey);
      scheduleSave();
      showMessage("Supporting docs uploaded.", "success");
    } catch (err) {
      showMessage(err.message || "Upload failed.", "error");
    }
  }

  async function extractRfp(uploadId) {
    if (!uploadId) {
      showMessage("Upload a file before running extraction.", "error");
      return;
    }
    state.allowAugment = true;
    state.isExtracting = true;
    if (els.extractStatus) {
      els.extractStatus.classList.remove("hidden");
      els.extractStatus.textContent = "Extracting RFP... please wait.";
    }
    clearMessage();
    setButtonLoading(els.extractBtn, "Analyzing RFP...");
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 180000);
      const res = await fetch(`/api/rfp-extract/${uploadId}`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Extraction failed (${res.status})`);
      }
      const data = await res.json();
      state.extracted = data;
      let hasContent = renderExtraction();
      if (!hasContent) {
        const refreshed = await fetchOpportunityExtraction();
        hasContent = hasExtractionContent(refreshed);
      }
      if (!hasContent && state.allowAugment) {
        if (els.extractStatus) {
          els.extractStatus.classList.remove("hidden");
          els.extractStatus.textContent = "Generating fallback with AI...";
        }
        hasContent = await augmentExtractionFromGeneration();
      }
      if (data.warning) {
        showMessage(data.warning, "error");
      }
      handleStepAvailability();
      showMessage("Extraction complete.", "success");
      scheduleSave();
    } catch (err) {
      const msg = err?.message || "";
      if (err?.name === "AbortError" || msg.toLowerCase().includes("aborted")) {
        showMessage("Extraction timed out. Please try again.", "error");
      } else {
        showMessage(msg || "Extraction failed.", "error");
      }
      if (els.extractStatus) {
        els.extractStatus.classList.remove("hidden");
        els.extractStatus.textContent = msg || "Extraction failed.";
      }
    } finally {
      setButtonLoading(els.extractBtn, null);
      state.isExtracting = false;
      if (els.extractStatus && !state.extracted) {
        els.extractStatus.classList.remove("hidden");
        els.extractStatus.textContent = "No extraction results yet. Try running extraction again.";
      }
    }
  }

  function renderExtraction() {
    if (!els.extractResults) return false;
    const root = state.extracted || {};
    const extracted = getExtractedObject(root);
    if (!extracted || Object.keys(extracted).length === 0) {
      renderGenerateOptions({});
      if (els.extractStatus) {
        els.extractStatus.classList.remove("hidden");
        if (state.isExtracting || augmentingExtraction) {
          els.extractStatus.textContent = "Extracting RFP... please wait.";
        } else {
          els.extractStatus.textContent = "No extraction results yet. Try running extraction again.";
        }
      }
      els.extractResults.classList.add("hidden");
      return false;
    }
    const summary =
      extracted.summary ||
      extracted.scope_of_work ||
      (root.discovery && root.discovery.summary) ||
      root.summary ||
      "";
    const checklist = []
      .concat(extracted.required_documents || [])
      .concat(extracted.required_forms || [])
      .concat(extracted.checklist || [])
      .concat(extracted.compliance_terms || [])
      .concat((root.discovery && root.discovery.requirements) || [])
      .filter(Boolean);

    const dates = normalizeDates(extracted, root);

    if (els.summaryText) {
      let displaySummary = summary || "No summary available yet.";
      if (displaySummary.length > 500) {
        displaySummary = displaySummary.substring(0, 497) + "...";
      }
      els.summaryText.textContent = displaySummary;
    }

    if (els.checklistItems) {
      els.checklistItems.innerHTML = "";

      const normalize = (s) => (s || "").trim().toLowerCase().replace(/\s+/g, " ");

      const narratives = extracted.narrative_sections || [];
      const narrativeNames = narratives.map((n) => (typeof n === "string" ? n : n.name)).filter(Boolean);
      const seenNarratives = new Set();
      const uniqueNarratives = narrativeNames.filter((name) => {
        const key = normalize(name);
        if (seenNarratives.has(key)) return false;
        seenNarratives.add(key);
        return true;
      });

      const forms = extracted.attachments_forms || [];
      const otherForms = extracted.required_forms || [];
      const seenForms = new Set();
      const allForms = [...forms, ...otherForms].filter((name) => {
        const key = normalize(name);
        if (seenForms.has(key)) return false;
        seenForms.add(key);
        return true;
      });

      if (uniqueNarratives.length) {
        const aiHeader = document.createElement("li");
        aiHeader.className = "checklist-header";
        aiHeader.innerHTML = "<strong>📝 AI Will Generate:</strong>";
        els.checklistItems.appendChild(aiHeader);

        uniqueNarratives.forEach((item) => {
          const li = document.createElement("li");
          li.className = "checklist-narrative";
          li.textContent = item;
          els.checklistItems.appendChild(li);
        });
      }

      if (allForms.length) {
        const formsHeader = document.createElement("li");
        formsHeader.className = "checklist-header";
        formsHeader.innerHTML = "<strong>📎 You Need to Provide:</strong>";
        els.checklistItems.appendChild(formsHeader);

        allForms.forEach((item) => {
          const li = document.createElement("li");
          li.className = "checklist-form";
          li.textContent = item;
          els.checklistItems.appendChild(li);
        });
      }

      if (!uniqueNarratives.length && !allForms.length) {
        els.checklistItems.innerHTML = `<li>No checklist items detected yet.</li>`;
      }
    }

    if (els.keyDates) {
      els.keyDates.innerHTML = "";
      if (Array.isArray(dates) && dates.length) {
        dates.slice(0, 5).forEach((d) => {
          const row = document.createElement("div");
          row.textContent = `${d.title || "Date"} - ${d.due_date || d.date || ""}`;
          els.keyDates.appendChild(row);
        });
      } else if (root.due_date) {
        els.keyDates.textContent = `Due date: ${root.due_date}`;
      } else {
        els.keyDates.textContent = "No key dates captured.";
      }
    }

    els.extractResults.classList.remove("hidden");
    const hasContent = Boolean(
      (summary && summary.trim()) || (checklist && checklist.length) || (dates && dates.length)
    );
    if (els.extractStatus) {
      if (!hasContent) {
        els.extractStatus.classList.remove("hidden");
        if (state.isExtracting || augmentingExtraction) {
          els.extractStatus.textContent = "Extracting RFP... please wait.";
        } else if (state.allowAugment) {
          els.extractStatus.textContent =
            "No key details yet. Try rerunning extraction or upload a clearer document.";
        } else {
          els.extractStatus.textContent = "No extraction results yet. Try running extraction again.";
        }
      } else {
        els.extractStatus.classList.add("hidden");
        els.extractStatus.textContent = "";
      }
    }
    // Narrative requirements panel
    if (els.extractResults) {
      let narrativeDetails = document.getElementById("narrativeDetails");
      if (!narrativeDetails) {
        narrativeDetails = document.createElement("div");
        narrativeDetails.id = "narrativeDetails";
        narrativeDetails.className = "narrative-details-panel";
        els.extractResults.appendChild(narrativeDetails);
      }
      const narratives = extracted.narrative_sections || [];
      if (narratives.length) {
        let html = "<h4>📝 Sections AI Will Generate:</h4>";
        html += "<div class='narrative-list'>";
        narratives.forEach((n) => {
          const name = typeof n === "string" ? n : n.name;
          const reqs = typeof n === "object" ? n.requirements : "";
          const limit = n && typeof n === "object" && n.page_limit
            ? `${n.page_limit} pages`
            : n && typeof n === "object" && n.word_limit
            ? `${n.word_limit} words`
            : "";
          html += `<div class="narrative-item">
            <strong>${name || ""}</strong>
            ${limit ? `<span class="limit-badge">${limit}</span>` : ""}
            ${reqs ? `<p class="narrative-reqs">${reqs}</p>` : ""}
          </div>`;
        });
        html += "</div>";
        narrativeDetails.innerHTML = html;
      } else {
        narrativeDetails.innerHTML = "";
      }
    }
    renderGenerateOptions(extracted);
    handleStepAvailability();
    if (state.sessionId && window.aiChat) {
      window.aiChat.enable(true);
    }
    return hasContent;
  }

  function renderGenerateOptions(extracted) {
    if (!els.generateOptions) return;

    const narratives = (extracted && extracted.narrative_sections) || [];

    // Fallback: show a single project response option if nothing was extracted
    if (!narratives.length) {
      els.generateOptions.innerHTML = `
        <div class="generate-option selected" data-section="Project Response">
          <div class="option-header">
            <input type="checkbox" checked>
            <div class="option-content">
              &#128203; <div>
                <strong>Project Response</strong>
                <div class="section-blurb">
                  <span class="blurb-short">Based on RFP requirements</span>
                  <span class="blurb-full" hidden>Based on RFP requirements</span>
                  <button class="blurb-toggle" type="button" aria-expanded="false" title="Show full description">…</button>
                </div>
              </div>
            </div>
          </div>
          <div class="section-instructions">
            <div class="instruction-row">
              <textarea class="section-instruction-input" rows="1" data-section="project_response"
                   placeholder="Add specific context for this section (optional)"></textarea>
              <button type="button" class="instruction-toggle" aria-expanded="false" title="Expand instructions">Expand</button>
            </div>
          </div>
          <div class="section-support" data-section="project_response">
            <div class="support-actions">
              <button type="button" class="support-attach-btn" data-section="project_response">&#128228; Attach docs</button>
              <input type="file" class="support-file-input" data-section="project_response" hidden multiple accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png,.gif,.webp" />
            </div>
            <div class="support-chips" data-section="project_response"></div>
          </div>
        </div>
      `;
      bindOptionCardEvents();
      return;
    }

    let html = "";
    narratives.forEach((section, index) => {
      const name = typeof section === "string" ? section : section.name || "Section";
      const requirements = typeof section === "object" ? section.requirements || "" : "";
      const safeReq = escapeHtml(requirements || "Required narrative section");
      const shortReq = safeReq.length > 90 ? `${safeReq.substring(0, 87)}...` : safeReq;
      const icon = index % 2 === 0 ? "&#128203;" : "&#128196;";
      const sectionKey = name.toLowerCase().replace(/[^a-z0-9]+/g, "_");

      html += `
        <div class="generate-option selected" data-section="${name}">
          <div class="option-header">
            <input type="checkbox" checked>
            <div class="option-content">
              ${icon} <div>
                <strong>${escapeHtml(name)}</strong>
                <div class="section-blurb">
                  <span class="blurb-short">${shortReq || "Required narrative section"}</span>
                  <span class="blurb-full" hidden>${safeReq || "Required narrative section"}</span>
                  <button class="blurb-toggle" type="button" aria-expanded="false" title="Show full description">…</button>
                </div>
              </div>
            </div>
          </div>
          <div class="section-instructions">
            <div class="instruction-row">
              <textarea class="section-instruction-input" rows="1" data-section="${sectionKey}"
                   placeholder="Add specific details for this section (e.g., pricing, personnel names)"></textarea>
              <button type="button" class="instruction-toggle" aria-expanded="false" title="Expand instructions">Expand</button>
            </div>
          </div>
          <div class="section-support" data-section="${sectionKey}">
            <div class="support-actions">
              <button type="button" class="support-attach-btn" data-section="${sectionKey}">&#128228; Attach docs</button>
              <input type="file" class="support-file-input" data-section="${sectionKey}" hidden multiple accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png,.gif,.webp" />
            </div>
            <div class="support-chips" data-section="${sectionKey}"></div>
          </div>
        </div>
      `;
    });

    els.generateOptions.innerHTML = html;
    bindOptionCardEvents();
  }

  function bindOptionCardEvents() {
    if (!els.generateOptions) return;

    const autoSize = (el) => {
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${Math.min(240, el.scrollHeight)}px`;
    };

    els.generateOptions.querySelectorAll(".generate-option").forEach((card) => {
      const header = card.querySelector(".option-header") || card;
      const checkbox = card.querySelector("input[type='checkbox']");

      header.addEventListener("click", (e) => {
        if (
          e.target.classList.contains("section-instruction-input") ||
          e.target.classList.contains("blurb-toggle") ||
          e.target.classList.contains("instruction-toggle")
        )
          return;
        card.classList.toggle("selected");
        if (checkbox) checkbox.checked = card.classList.contains("selected");
      });
    });

    els.generateOptions.querySelectorAll(".section-instruction-input").forEach((input) => {
      input.addEventListener("click", (e) => e.stopPropagation());
      input.addEventListener("input", () => autoSize(input));
      autoSize(input);
    });

    els.generateOptions.querySelectorAll(".instruction-toggle").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const wrapper = btn.closest(".section-instructions");
        const input = wrapper?.querySelector(".section-instruction-input");
        if (!input) return;
        const expanded = input.classList.toggle("expanded");
        btn.setAttribute("aria-expanded", expanded ? "true" : "false");
        btn.textContent = expanded ? "Collapse" : "Expand";
        input.style.maxHeight = expanded ? "240px" : "80px";
        autoSize(input);
      });
    });

    els.generateOptions.querySelectorAll(".blurb-toggle").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const card = btn.closest(".generate-option");
        const full = card?.querySelector(".blurb-full");
        const short = card?.querySelector(".blurb-short");
        if (!full || !short) return;
        const expanded = !full.hasAttribute("hidden");
        if (expanded) {
          full.setAttribute("hidden", "");
          short.classList.remove("hidden");
          btn.textContent = "…";
          btn.setAttribute("aria-expanded", "false");
        } else {
          full.removeAttribute("hidden");
          short.classList.add("hidden");
          btn.textContent = "Hide";
          btn.setAttribute("aria-expanded", "true");
        }
      });
    });

    els.generateOptions.querySelectorAll(".support-attach-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sectionKey = btn.dataset.section;
        const input = els.generateOptions.querySelector(`.support-file-input[data-section="${sectionKey}"]`);
        input?.click();
      });
    });

    els.generateOptions.querySelectorAll(".support-file-input").forEach((input) => {
      input.addEventListener("change", (e) => {
        e.stopPropagation();
        const sectionKey = input.dataset.section;
        const files = input.files;
        if (files && files.length) {
          uploadSectionFiles(sectionKey, files);
        }
        input.value = "";
      });
    });

    els.generateOptions.querySelectorAll(".support-chips").forEach((chips) => {
      const sectionKey = chips.dataset.section;
      chips.addEventListener("click", (e) => {
        const btn = e.target.closest(".chip-remove");
        if (!btn) return;
        const chip = btn.closest(".chip");
        const docId = chip?.dataset.docId;
        if (!docId) return;
        removeDocFromSection(sectionKey, docId);
      });
      renderSectionChips(sectionKey);
    });
  }

  function getSectionInstructions() {
    const instructions = {};
    if (!els.generateOptions) {
      console.warn("[AI Studio] generateOptions element not found");
      return instructions;
    }
    const inputs = els.generateOptions.querySelectorAll(".section-instruction-input");
    console.log(`[AI Studio] Found ${inputs.length} section instruction inputs`);
    inputs.forEach((input) => {
      const section = input.dataset.section;
      const value = input.value.trim();
      console.log(
        `[AI Studio] Section "${section}": "${value.substring(0, 50)}${value.length > 50 ? "..." : ""}"`
      );
      if (section && value) {
        instructions[section] = value;
      }
    });
    console.log("[AI Studio] Collected section instructions:", instructions);
    return instructions;
  }

  function getInstructionUploadIds() {
    const ids = [];
    if (state.upload?.id) ids.push(state.upload.id);
    const sectionDocs = state.sectionDocs || {};
    Object.values(sectionDocs).forEach((docs) => {
      (docs || []).forEach((d) => {
        if (d?.id || d?.id === 0) ids.push(d.id);
      });
    });
    return [...new Set(ids.map((v) => (typeof v === "string" && /^\d+$/.test(v) ? Number(v) : v)))];
  }

  async function augmentExtractionFromGeneration() {
    if (!state.opportunityId || augmentingExtraction || !state.allowAugment) return false;
    augmentingExtraction = true;
    if (els.extractStatus) {
      els.extractStatus.classList.remove("hidden");
      els.extractStatus.textContent = "Generating fallback with AI...";
    }
    try {
      const payload = {
        instruction_upload_ids: getInstructionUploadIds(),
      };
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30000);
      const res = await fetch(
        `/api/opportunities/${encodeURIComponent(state.opportunityId)}/generate`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": getCsrf(),
          },
          body: JSON.stringify(payload),
        }
      );
      clearTimeout(timeout);
      if (!res.ok) {
        return false;
      }
      const data = await res.json();
      const docs = data.documents || {};
      const augmented = {
        summary:
          docs.submission_instructions ||
          (Array.isArray(docs.submission_checklist) ? docs.submission_checklist.join(". ") : "") ||
          (typeof docs.cover_letter === "string" ? docs.cover_letter.split("\n").slice(0, 2).join(" ") : ""),
        checklist: docs.submission_checklist || docs.checklist || [],
        key_dates: docs.calendar_events || [],
      };
      const existing = state.extracted?.extracted || state.extracted || {};
      const currentExtracted = state.extracted?.extracted?.extracted || state.extracted?.extracted || existing;
      state.extracted = {
        ...(state.extracted || {}),
        extracted: {
          ...(state.extracted?.extracted || {}),
          extracted: { ...currentExtracted, ...augmented },
        },
      };
      const hasContent = renderExtraction();
      if (hasContent) {
        showMessage("Used AI generation to fill summary/checklist/dates.", "success");
        return true;
      }
    } catch (err) {
      showMessage(err.message || "Fallback generation failed.", "error");
    } finally {
      augmentingExtraction = false;
      if (els.extractStatus && !state.isExtracting && !state.extracted?.extracted) {
        els.extractStatus.classList.remove("hidden");
        els.extractStatus.textContent = "No extraction results yet. Try running extraction again.";
      }
    }
    return false;
  }

  async function fetchOpportunityExtraction() {
    if (!state.opportunityId) return;
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(state.opportunityId)}/extracted`, {
        credentials: "include",
      });
      if (!res.ok) return;
      const data = await res.json();
      const hasNew = hasExtractionContent(data);
      const hasExisting = hasExtractionContent(state.extracted);
      if (hasNew || !hasExisting) {
        state.extracted = data;
        const hasContent = renderExtraction();
        if (!hasContent && state.allowAugment) {
          await augmentExtractionFromGeneration();
        }
      }
    } catch (err) {
      showMessage(err.message || "Could not load extracted data.", "error");
    }
    handleStepAvailability();
    return state.extracted;
  }

  function formatSoqText(val) {
    if (!val) return "";
    if (typeof val === "string") return val;
    if (typeof val === "object") {
      return Object.entries(val)
        .map(([k, v]) => `${k.replace(/_/g, " ")}:\n${Array.isArray(v) ? v.join("\n") : String(v || "")}`)
        .join("\n\n");
    }
    return String(val || "");
  }

  function renderDocuments() {
    if (!els.documentEditor || !els.editableContent || !els.previewContent) return;
    els.documentEditor.classList.remove("hidden");
    const content = sanitizeHtml(state.documents[state.currentDoc] || "");
    els.editableContent.innerHTML = content;
    updatePreview();
    updateWordCount();
    els.editorTabs.forEach((tab) => {
      const doc = tab.dataset.doc;
      tab.classList.toggle("active", doc === state.currentDoc);
    });
  }

  function renderDocumentTabs() {
    const tabsContainer = document.querySelector(".editor-tabs");
    if (!tabsContainer) return;

    tabsContainer.innerHTML = "";

    (state.responseSections || []).forEach((section, index) => {
      if (!section) return;
      const key = normalizeSectionKey(section);
      const isActive = state.currentDoc === key || (!state.currentDoc && index === 0);
      const tab = document.createElement("button");
      tab.className = "editor-tab" + (isActive ? " active" : "");
      tab.type = "button";
      tab.dataset.doc = key;
      tab.innerHTML = `&#128203; ${section}`;
      tab.addEventListener("click", () => switchDocument(key));
      tabsContainer.appendChild(tab);
    });

    if (!state.currentDoc && state.responseSections?.length) {
      state.currentDoc = normalizeSectionKey(state.responseSections[0]);
    }

    els.editorTabs = tabsContainer.querySelectorAll(".editor-tab");
    setTimeout(updateTabNavArrows, 100);
  }

  function normalizeSectionKey(section) {
    return (section || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  }

  function deriveSectionsFromDocuments(docs) {
    if (!docs || typeof docs !== "object") return [];
    const skipKeys = new Set(["cover", "responses", "soq", "cover_letter", "soq_body"]);
    const keys = Object.keys(docs).filter((k) => !skipKeys.has(k));
    if (!keys.length) return [];
    return keys.map((k) => titleCaseFromKey(k));
  }

  function titleCaseFromKey(key) {
    return (key || "")
      .replace(/_/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .split(" ")
      .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : ""))
      .join(" ");
  }

  function updateTabNavArrows() {
    const tabsContainer = document.querySelector(".editor-tabs");
    const leftArrow = document.querySelector(".tab-nav-left");
    const rightArrow = document.querySelector(".tab-nav-right");

    if (!tabsContainer || !leftArrow || !rightArrow) return;

    const canScrollLeft = tabsContainer.scrollLeft > 0;
    const canScrollRight = tabsContainer.scrollLeft < tabsContainer.scrollWidth - tabsContainer.clientWidth - 1;

    leftArrow.style.display = tabsContainer.scrollWidth > tabsContainer.clientWidth ? "flex" : "none";
    rightArrow.style.display = tabsContainer.scrollWidth > tabsContainer.clientWidth ? "flex" : "none";

    leftArrow.disabled = !canScrollLeft;
    rightArrow.disabled = !canScrollRight;
  }

  function scrollTabs(direction) {
    const tabsContainer = document.querySelector(".editor-tabs");
    if (!tabsContainer) return;

    const scrollAmount = 200;
    tabsContainer.scrollBy({
      left: direction === "left" ? -scrollAmount : scrollAmount,
      behavior: "smooth",
    });

    setTimeout(updateTabNavArrows, 300);
  }

  function toggleFullscreen() {
    const target = document.getElementById("documentEditor") || document.documentElement;
    if (!target) return;

    const requestFs =
      target.requestFullscreen ||
      target.webkitRequestFullscreen ||
      target.mozRequestFullScreen ||
      target.msRequestFullscreen;
    const exitFs =
      document.exitFullscreen ||
      document.webkitExitFullscreen ||
      document.mozCancelFullScreen ||
      document.msExitFullscreen;

    if (!document.fullscreenElement && requestFs) {
      requestFs.call(target).catch(() => showMessage("Fullscreen not available in this browser.", "error"));
    } else if (document.fullscreenElement && exitFs) {
      exitFs.call(document);
    }
  }

  async function generateDocuments() {
    if (!state.opportunityId) {
      showMessage("Select an opportunity before generating.", "error");
      return;
    }
    clearMessage();
    if (els.generateError) {
      els.generateError.classList.add("hidden");
    }
    setButtonLoading(els.generateBtn, "Generating...");
    try {
      const payload = {
        instruction_upload_ids: getInstructionUploadIds(),
      };
      if (els.customInstructions && els.customInstructions.value.trim()) {
        payload.custom_instructions = els.customInstructions.value.trim();
      }
      const sectionInstructions = getSectionInstructions();
      if (Object.keys(sectionInstructions).length > 0) {
        payload.section_instructions = sectionInstructions;
      }
      console.log("[AI Studio] Sending payload:", JSON.stringify(payload, null, 2));
      const res = await fetch(
        `/api/opportunities/${encodeURIComponent(state.opportunityId)}/generate`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": getCsrf(),
          },
          body: JSON.stringify(payload),
        }
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Generation failed (${res.status})`);
      }
      const data = await res.json();
      const docs = data.documents || {};
      const narrativeSections =
        state.extracted?.extracted?.narrative_sections ||
        state.extracted?.extracted?.extracted?.narrative_sections ||
        docs.narrative_sections_list ||
        [];

      state.responseSections = (narrativeSections || [])
        .map((s) => (typeof s === "string" ? s : s?.name || s?.title || "Section"))
        .filter(Boolean);

      if (!state.responseSections.length && docs.response_sections) {
        state.responseSections = Object.keys(docs.response_sections);
      }

      if (!state.responseSections.length) {
        state.responseSections = ["Project Response"];
      }

      state.documents = {};
      const responseSections = docs.response_sections || {};

      // Map API response sections by normalized key
      Object.entries(responseSections).forEach(([key, value]) => {
        const normKey = normalizeSectionKey(key);
        state.documents[normKey] = typeof value === "string" ? value : formatSoqText(value);
      });

      // Also map using exact section names from extraction if available
      state.responseSections.forEach((sectionName) => {
        const normKey = normalizeSectionKey(sectionName);
        if (!state.documents[normKey] && responseSections[sectionName]) {
          const value = responseSections[sectionName];
          state.documents[normKey] = typeof value === "string" ? value : formatSoqText(value);
        }
      });

      if (data.signature_url && state.documents) {
        const coverKey = Object.keys(state.documents).find((k) => {
          if (!k) return false;
          const lower = k.toLowerCase();
          return (
            lower.includes("cover") ||
            lower.includes("transmittal") ||
            lower.includes("letter") ||
            lower === "cover_letter"
          );
        });

        console.log("Signature URL available:", data.signature_url);
        console.log("Looking for cover letter, found key:", coverKey);

        if (coverKey && state.documents[coverKey]) {
          const content = state.documents[coverKey];
          const hasSignature =
            /<img[^>]+src=[\"'][^\"']*[\"'][^>]*>/i.test(content) && /signature/i.test(content);

          if (!hasSignature) {
            const signatory = data.company_profile?.authorized_signatory || {};
            const primary = data.company_profile?.primary_contact || {};
            const sigName = signatory.name || primary.name || "";
            const sigTitle = signatory.title || primary.title || "";
            const companyName = data.company_profile?.legal_name || "";

            const sigBlock = `<br><br>Sincerely,<br><br>
<img src="${data.signature_url}" alt="Signature" style="max-width: 200px; height: auto; margin: 10px 0;" onerror="this.style.display='none'"><br>
<strong>${escapeHtml(sigName || "")}</strong><br>
${sigTitle ? `${escapeHtml(sigTitle)}<br>` : ""}
${escapeHtml(companyName)}`;

            if (!/sincerely|regards|respectfully/i.test(content.slice(-500))) {
              state.documents[coverKey] += sigBlock;
              console.log("Added signature block to", coverKey);
            }
          }
        }
      }

      state.currentDoc = state.responseSections.length
        ? normalizeSectionKey(state.responseSections[0])
        : null;
      renderDocumentTabs();

      // If extraction pane is still empty, backfill summary/checklist/dates from generated docs.
      const augmentedExtraction = {
        summary:
          docs.submission_instructions ||
          (Array.isArray(docs.submission_checklist) ? docs.submission_checklist.join(". ") : "") ||
          (typeof docs.cover_letter === "string" ? docs.cover_letter.split("\n").slice(0, 2).join(" ") : ""),
        checklist: docs.submission_checklist || docs.checklist || [],
        key_dates: docs.calendar_events || [],
      };
      if (!hasExtractionContent(state.extracted)) {
        const existingExtracted = getExtractedObject(state.extracted);
        state.extracted = {
          ...(state.extracted || {}),
          extracted: { ...existingExtracted, ...augmentedExtraction },
        };
        renderExtraction();
      }

      renderDocuments();
      handleStepAvailability();
      showMessage("Documents generated. Review and edit before export.", "success");
      scheduleSave();
    } catch (err) {
      showMessage(err.message || "Failed to generate documents.", "error");
      if (els.generateError) {
        els.generateError.classList.remove("hidden");
        els.generateError.textContent = err.message || "Generation failed.";
      }
    } finally {
      setButtonLoading(els.generateBtn, null);
    }
  }

  function updatePreview() {
    if (!els.editableContent || !els.previewContent) return;
    els.previewContent.innerHTML = sanitizeHtml(els.editableContent.innerHTML);
  }

  function updateWordCount() {
    if (!els.editableContent || !els.wordCount) return;
    const text = (els.editableContent.innerText || "").trim();
    const words = text ? text.split(/\s+/).filter(Boolean).length : 0;
    els.wordCount.textContent = `${words} word${words === 1 ? "" : "s"}`;
  }

  function switchDocument(doc) {
    if (!doc) return;
    if (state.currentDoc && els.editableContent) {
      state.documents[state.currentDoc] = sanitizeHtml(els.editableContent.innerHTML || "");
    }
    state.currentDoc = doc;
    renderDocuments();
    document.querySelectorAll(".editor-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.doc === doc);
    });
    scheduleSave();
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveSession(false), 800);
  }

  function buildSessionState() {
    const sections =
      (Array.isArray(state.responseSections) && state.responseSections.filter(Boolean)) ||
      deriveSectionsFromDocuments(state.documents);
    const latestSections = sections.map((sectionName) => {
      const key = normalizeSectionKey(sectionName);
      const html = (state.documents && state.documents[key]) || "";
      return { section: sectionName, answer: stripHtml(html) };
    });
    const coverDraft = stripHtml(state.documents?.cover || "");
    const soqDraft = stripHtml(state.documents?.responses || state.documents?.soq || "");
    return {
      opportunityId: state.opportunityId,
      opportunityLabel: state.opportunityLabel,
      upload: state.upload,
      extracted: state.extracted,
      documents: state.documents,
      currentDoc: state.currentDoc,
      currentStep: state.currentStep,
      notes: els.customInstructions?.value || "",
      sectionDocs: state.sectionDocs || {},
      sections,
      latestSections,
      coverDraft,
      soqDraft,
    };
  }

  async function saveSession(manual = false, allowRetry = true) {
    const payload = buildSessionState();
    if (!payload.opportunityId && !payload.documents.cover && !payload.documents.responses) {
      return;
    }
    if (saveInFlight) {
      saveQueued = true;
      queuedManualSave = queuedManualSave || manual;
      return;
    }
    saveInFlight = true;
    try {
      const res = await fetch("/api/ai-sessions/save", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrf(),
        },
        body: JSON.stringify({
          session_id: state.sessionId,
          opportunity_id: payload.opportunityId,
          name: payload.opportunityLabel || null,
          state: payload,
        }),
      });
      if (res.status === 404 && allowRetry) {
        state.sessionId = null;
        saveInFlight = false;
        return await saveSession(manual, false);
      }
      if (!res.ok) throw new Error("Save failed");
      const data = await res.json();
      state.sessionId = data.session_id;
      updateCurrentSessionDisplay();
      showSaveIndicator(manual ? "Saved" : "Autosaved");
      if (window.aiChat && state.sessionId) {
        window.aiChat.enable(true);
        window.aiChat.loadHistory(state.sessionId);
      }
    } catch (err) {
      showSaveIndicator(err.message || "Save failed", true);
    } finally {
      saveInFlight = false;
      if (saveQueued) {
        const manualNext = queuedManualSave;
        saveQueued = false;
        queuedManualSave = false;
        await saveSession(manualNext);
      }
    }
  }

  async function loadSession(sessionId) {
    if (!sessionId) return;
    try {
      showMessage("Loading saved session...", "info");
      const res = await fetch(`/api/ai-sessions/${sessionId}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load session");
      const data = await res.json();
      state.sessionId = data.id;
      const st = data.state || {};
      state.opportunityId = st.opportunityId || "";
      state.opportunityLabel = st.opportunityLabel || "";
      state.upload = st.upload || null;
      state.extracted = st.extracted || null;
      state.documents = st.documents || { cover: "", responses: "" };
      state.sectionDocs = st.sectionDocs || {};
      state.responseSections =
        (Array.isArray(st.sections) && st.sections.length && st.sections) ||
        (Array.isArray(st.responseSections) && st.responseSections.length && st.responseSections) ||
        deriveSectionsFromDocuments(state.documents) ||
        state.responseSections ||
        [];
      if (!state.responseSections.length) {
        state.responseSections = ["Project Response"];
      }
      if (state.documents && !state.documents.responses && state.documents.soq) {
        state.documents.responses = state.documents.soq;
      }
      state.currentDoc = st.currentDoc || normalizeSectionKey(state.responseSections[0] || "cover");
      state.currentStep = st.currentStep || state.currentStep || 1;
      if (els.customInstructions) {
        els.customInstructions.value = st.notes || "";
      }
      if (els.genOpportunity && state.opportunityId) {
        els.genOpportunity.value = state.opportunityId;
      }
      if (state.opportunityId) {
        await fetchExistingDocuments(state.opportunityId, state.upload?.id);
      }
      if (state.upload) {
        renderUpload(state.upload);
      }
      if (state.extracted) {
        renderExtraction();
        els.extractResults?.classList.remove("hidden");
      }
      renderDocumentTabs();
      if (state.documents) {
        renderDocuments();
      }
      const hasDocs = Boolean(
        (state.documents?.cover && state.documents.cover.trim()) ||
          (state.documents?.responses && state.documents.responses.trim())
      );
      const computedStep = hasDocs ? 3 : state.extracted ? 2 : state.upload ? 1 : 1;
      const targetStep = Math.min(4, Math.max(1, st.currentStep || computedStep));
      goToStep(targetStep);
      handleStepAvailability();
      showMessage("Session restored.", "success");
      updateCurrentSessionDisplay();
      if (window.aiChat && state.sessionId) {
        window.aiChat.enable(true);
        window.aiChat.loadHistory(state.sessionId);
      }
    } catch (err) {
      showMessage(err.message || "Could not load session.", "error");
    }
  }

  async function loadLatestSession() {
    try {
      const res = await fetch("/api/ai-sessions/recent?limit=1", { credentials: "include" });
      if (!res.ok) throw new Error("No previous sessions found.");
      const data = await res.json();
      const latest = Array.isArray(data) ? data[0] : null;
      if (!latest) {
        showMessage("No saved sessions yet.", "error");
        return;
      }
      await loadSession(latest.id);
    } catch (err) {
      showMessage(err.message || "Unable to load previous session.", "error");
    }
  }

  // ============================================
  // SESSION PICKER FUNCTIONALITY
  // ============================================

  let selectedSessionIds = new Set();

  function openSessionModal() {
    selectedSessionIds = new Set();
    updateSelectionDisplay();
    els.sessionModalOverlay?.classList.add("active");
    els.sessionModal?.classList.add("active");
    fetchSavedSessions();
  }

  function closeSessionModal() {
    els.sessionModalOverlay?.classList.remove("active");
    els.sessionModal?.classList.remove("active");
  }

  async function fetchSavedSessions() {
    if (!els.sessionList) return;

    els.sessionList.innerHTML = '<div class="session-loading">Loading saved drafts...</div>';
    selectedSessionIds = new Set();
    updateSelectionDisplay();

    try {
      const res = await fetch("/api/ai-sessions/recent?limit=50", {
        credentials: "include",
        cache: "no-store",
      });

      if (!res.ok) throw new Error("Failed to load sessions");

      const sessions = await res.json();
      renderSessionList(sessions);
    } catch (err) {
      console.error("Failed to fetch sessions:", err);
      els.sessionList.innerHTML = '<div class="session-empty">Failed to load saved drafts</div>';
    }
  }

  function renderSessionList(sessions) {
    if (!els.sessionList) return;

    const activeSessions = (sessions || []).filter(
      (s) => !s.deleted_at && !s.is_deleted && s.status !== "deleted"
    );

    let filtered = activeSessions;
    if (state.opportunityId) {
      const currentOpp = String(state.opportunityId);
      filtered = activeSessions.filter((s) => String(s.opportunity_id) === currentOpp);
    }

    if (!filtered.length) {
      els.sessionList.innerHTML = `
      <div class="session-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        <div>No saved drafts yet</div>
        <div style="font-size: 12px; margin-top: 4px;">Your work will be auto-saved as you edit</div>
      </div>
    `;
      updateSessionCount(0);
      return;
    }

    const html = filtered
      .map((session) => {
        const isActive = String(state.sessionId) === String(session.id);
        const progress = getSessionProgress(session);
        const updatedAt = formatRelativeTime(session.updated_at);
        const title = session.name || session.opportunity_title || "Untitled Draft";

        return `
      <div class="session-item ${isActive ? "active" : ""}" data-session-id="${session.id}">
        <label class="session-select">
          <input type="checkbox" class="session-checkbox" data-select-id="${session.id}" ${selectedSessionIds.has(String(session.id)) ? "checked" : ""} />
        </label>
        <div class="session-item-icon">📄</div>
        <div class="session-item-content">
          <div class="session-item-title">${escapeHtml(title)}</div>
          <div class="session-item-meta">
            <span>${updatedAt}</span>
            <span>•</span>
            <div class="session-item-progress">
              <div class="session-progress-bar">
                <div class="session-progress-fill" style="width: ${progress}%"></div>
              </div>
              <span>${progress}%</span>
            </div>
          </div>
        </div>
        <div class="session-item-actions">
          <button type="button" class="session-action-btn load" data-load-id="${session.id}" title="Load draft">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 4h16v12H5.17L4 17.17V4z"/>
              <polyline points="8 8 12 12 16 8"/>
            </svg>
          </button>
          <button type="button" class="session-action-btn delete" data-delete-id="${session.id}" title="Delete draft">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    `;
      })
      .join("");

    els.sessionList.innerHTML = html;
    updateSessionCount(filtered.length);

    els.sessionList.querySelectorAll("[data-load-id]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const sessionId = btn.dataset.loadId;
        if (sessionId) {
          await loadSession(parseInt(sessionId, 10));
          closeSessionModal();
        }
      });
    });

    els.sessionList.querySelectorAll(".session-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        const id = cb.dataset.selectId;
        if (!id) return;
        const strId = String(id);
        if (cb.checked) {
          selectedSessionIds.add(strId);
        } else {
          selectedSessionIds.delete(strId);
        }
        updateSelectionDisplay();
        updateSelectAllState();
      });
    });

    els.sessionList.querySelectorAll("[data-delete-id]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const sessionId = btn.dataset.deleteId;
        if (confirm("Delete this draft? This cannot be undone.")) {
          await deleteSession(parseInt(sessionId, 10));
          fetchSavedSessions();
        }
      });
    });
  }

  async function deleteSession(sessionId) {
    try {
      const res = await fetch(`/api/ai-sessions/${sessionId}`, {
        method: "DELETE",
        credentials: "include",
        headers: {
          "X-CSRF-Token": getCsrf(),
        },
      });

      if (!res.ok) throw new Error("Failed to delete session");

      if (state.sessionId === sessionId) {
        state.sessionId = null;
        updateCurrentSessionDisplay();
      }

      showSaveIndicator("Deleted");
    } catch (err) {
      console.error("Delete session error:", err);
      alert("Failed to delete draft");
    }
  }

  function startNewSession() {
    if (Object.keys(state.documents).length > 0) {
      if (!confirm("Start a new draft? Your current work is auto-saved.")) {
        return;
      }
    }

    state.sessionId = null;
    state.documents = {};
    state.responseSections = [];
    state.currentDoc = "";
    if (window.aiChat) {
      window.aiChat.clear();
      window.aiChat.enable(false);
    }

    if (els.editableContent) {
      els.editableContent.innerHTML = "";
    }
    if (els.previewContent) {
      els.previewContent.innerHTML = "";
    }

    renderDocumentTabs();
    handleStepAvailability();
    updateCurrentSessionDisplay();
    showSaveIndicator("New draft started");
  }

  function updateCurrentSessionDisplay() {
    if (!els.currentSessionName) return;

    if (state.sessionId) {
      els.currentSessionName.textContent = state.opportunityLabel || "Saved Draft";
      els.currentSessionTime.textContent = "• Auto-saved";
    } else {
      els.currentSessionName.textContent = "Unsaved Draft";
      els.currentSessionTime.textContent = "";
    }
  }

  function updateSessionCount(count) {
    if (els.sessionCount) {
      els.sessionCount.textContent = `${count} saved draft${count !== 1 ? "s" : ""}`;
    }
  }

  function updateSelectionDisplay() {
    const count = selectedSessionIds.size;
    if (els.sessionSelectionCount) {
      els.sessionSelectionCount.textContent = `${count} selected`;
    }
    if (els.bulkDeleteSessions) {
      els.bulkDeleteSessions.disabled = count === 0;
    }
    updateSelectAllState();
  }

  function updateSelectAllState() {
    if (!els.sessionSelectAll || !els.sessionList) return;
    const checkboxes = els.sessionList.querySelectorAll(".session-checkbox");
    if (!checkboxes.length) {
      els.sessionSelectAll.checked = false;
      els.sessionSelectAll.indeterminate = false;
      return;
    }
    const total = checkboxes.length;
    const selected = Array.from(checkboxes).filter((cb) => cb.checked).length;
    els.sessionSelectAll.checked = selected > 0 && selected === total;
    els.sessionSelectAll.indeterminate = selected > 0 && selected < total;
  }

  function formatRelativeTime(dateStr) {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  }

  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function getSessionProgress(session) {
    const total = Number(session.sections_total);
    const completed = Number(session.sections_completed);
    if (!Number.isNaN(total) && total > 0) {
      const pct = Math.round((Math.max(0, Math.min(completed, total)) / total) * 100);
      return Math.max(0, Math.min(100, pct));
    }

    const docs = session.state?.documents;
    if (docs && typeof docs === "object") {
      const keys = Object.keys(docs);
      const filled = keys.filter((k) => {
        const val = docs[k];
        return typeof val === "string" && val.trim().length > 0;
      });
      if (keys.length > 0 && filled.length > 0) {
        const pct = Math.round((filled.length / keys.length) * 100);
        return Math.max(10, Math.min(100, pct));
      }
    }

    if (session.has_cover_letter || session.has_soq) {
      return 66;
    }

    return 0;
  }

  function stripHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html || "";
    return div.textContent || "";
  }

  async function exportDocument(format) {
    if (!state.opportunityId) {
      showMessage("Select an opportunity before exporting.", "error");
      return;
    }
    const btn = format === "pdf" ? els.exportPdf : els.exportWord;
    setButtonLoading(btn, "Exporting...");
    try {
      state.documents[state.currentDoc] = els.editableContent?.innerHTML || "";
      const res = await fetch(
        `/api/opportunities/${encodeURIComponent(state.opportunityId)}/export?format=${format}`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": getCsrf(),
          },
          body: JSON.stringify({
            cover_letter: stripHtml(state.documents.cover),
            soq_body: stripHtml(state.documents.responses),
            title: state.extracted?.title || "",
            agency: state.extracted?.agency || "",
          }),
        }
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const ext = format === "pdf" ? "pdf" : "docx";
      a.href = url;
      a.download = `submission.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
      els.completionMessage?.classList.remove("hidden");
      if (els.progressFill) els.progressFill.style.width = "100%";
      if (els.progressPercent) els.progressPercent.textContent = "100% complete";
      showMessage("Export ready.", "success");
    } catch (err) {
      showMessage(err.message || "Export failed.", "error");
    } finally {
      setButtonLoading(btn, null);
    }
  }

  function setPreviewPage(index) {
    const sections = document.querySelectorAll(".preview-section");
    const total = Math.max(sections.length, 1);
    previewPageIndex = Math.max(0, Math.min(index, total - 1));
    const currentEl = document.getElementById("currentPage");
    const totalEl = document.getElementById("totalPages");
    const prevBtn = document.getElementById("prevPage");
    const nextBtn = document.getElementById("nextPage");

    if (totalEl) totalEl.textContent = total;
    if (currentEl) currentEl.textContent = sections.length ? previewPageIndex + 1 : 1;
    if (prevBtn) prevBtn.disabled = sections.length === 0 || previewPageIndex === 0;
    if (nextBtn) nextBtn.disabled = sections.length === 0 || previewPageIndex >= total - 1;

    const target = sections[previewPageIndex];
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function renderStep4Preview() {
    const previewContent = document.getElementById("previewPageContent");
    const sectionReviewList = document.getElementById("sectionReviewList");
    if (!previewContent || !sectionReviewList) return;

    const sections = state.responseSections || [];
    previewPageIndex = 0;
    let html = "";

    sections.forEach((sectionName, idx) => {
      const key = normalizeSectionKey(sectionName);
      const content = state.documents[key] || "";
      if (content.trim()) {
        html += `<div class="preview-section" data-section="${idx}">
          <h2 style="margin-top: ${idx > 0 ? "24pt" : "0"};">${escapeHtml(sectionName)}</h2>
          ${content}
        </div>`;
      }
    });

    previewContent.innerHTML = html || "<p>No content generated yet.</p>";

    sectionReviewList.innerHTML = sections
      .map((name, idx) => {
        const key = normalizeSectionKey(name);
        const hasContent = typeof state.documents[key] === "string" && state.documents[key].trim().length > 0;
        return `<div class="review-item">
          <span>${hasContent ? "&#10003;" : "&#9744;"}</span>
          <div><strong>${escapeHtml(name)}</strong><span>${hasContent ? "Generated" : "Not generated"}</span></div>
        </div>`;
      })
      .join("");

    setPreviewPage(0);
  }

  async function saveToRfpFolder() {
    if (!state.opportunityId) {
      showMessage("No opportunity selected", "error");
      return;
    }

    const statusEl = document.getElementById("saveFolderStatus");
    const btn = document.getElementById("saveToFolder");
    setButtonLoading(btn, "Saving...");

    try {
      const sections = state.responseSections || [];
      const combinedHtml = sections
        .map((name) => {
          const key = normalizeSectionKey(name);
          return state.documents[key] || "";
        })
        .join("\n\n");

      const filenameBase = state.opportunityLabel
        ? state.opportunityLabel.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")
        : "proposal";
      const filename = `${filenameBase || "proposal"}-${Date.now()}.html`;

      const res = await fetch(`/api/opportunities/${encodeURIComponent(state.opportunityId)}/save-package`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrf(),
        },
        body: JSON.stringify({
          content: combinedHtml,
          filename,
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Save failed");
      }

      if (statusEl) {
        statusEl.textContent = "Saved to RFP folder!";
        statusEl.style.color = "#16a34a";
      }
      showMessage("Package saved to documents folder", "success");
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = err.message || "Save failed";
        statusEl.style.color = "#dc2626";
      }
    } finally {
      setButtonLoading(btn, null);
    }
  }

  function bindEvents() {
    if (els.genOpportunity) {
      els.genOpportunity.addEventListener("change", (e) => {
        const select = e.target;
        state.opportunityId = select.value;
        state.opportunityLabel = select.options[select.selectedIndex]?.text || "";
        state.allowAugment = false;
        state.upload = null;
        state.extracted = null;
        state.existingDocs = [];
        state.sectionDocs = {};
        if (els.uploadedFile) els.uploadedFile.classList.add("hidden");
        if (els.uploadArea) els.uploadArea.style.display = "block";
        if (els.existingDocsList) {
          els.existingDocsList.innerHTML = `<div class="doc-empty">Loading documents...</div>`;
        }
        if (els.extractResults) els.extractResults.classList.add("hidden");
        switchDocTab("existing");
        handleStepAvailability();
        fetchExistingDocuments(state.opportunityId);
        scheduleSave();
      });
    }

    if (els.docTabButtons && els.docTabButtons.length) {
      els.docTabButtons.forEach((btn) => {
        btn.addEventListener("click", () => switchDocTab(btn.dataset.tab));
      });
    }

    if (els.existingDocsList) {
      els.existingDocsList.addEventListener("click", (e) => {
        const card = e.target.closest(".doc-card");
        if (!card) return;
        const uploadId = Number(card.dataset.uploadId);
        const doc = state.existingDocs.find((d) => Number(d.id) === uploadId);
        if (doc) {
          selectExistingDocument(doc);
        }
      });
    }

    if (els.uploadArea && els.rfpUploadInput) {
      els.uploadArea.addEventListener("click", () => els.rfpUploadInput?.click());
      els.uploadArea.addEventListener("dragover", (e) => {
        e.preventDefault();
        els.uploadArea.classList.add("drag-over");
      });
      els.uploadArea.addEventListener("dragleave", () => {
        els.uploadArea.classList.remove("drag-over");
      });
      els.uploadArea.addEventListener("drop", (e) => {
        e.preventDefault();
        els.uploadArea.classList.remove("drag-over");
        const file = e.dataTransfer?.files?.[0];
        if (file) uploadFile(file);
      });
      els.rfpUploadInput.addEventListener("change", (e) => {
        const file = e.target.files?.[0];
        if (file) uploadFile(file);
      });
    }

    if (els.removeFile) {
      els.removeFile.addEventListener("click", () => {
        state.upload = null;
        state.allowAugment = false;
        if (els.uploadedFile) els.uploadedFile.classList.add("hidden");
        if (els.uploadArea) els.uploadArea.style.display = "block";
        if (els.rfpUploadInput) els.rfpUploadInput.value = "";
        renderExistingDocuments();
        handleStepAvailability();
        scheduleSave();
      });
    }

    if (els.step1Next) {
      els.step1Next.addEventListener("click", () => goToStep(2));
    }
    if (els.step2Back) {
      els.step2Back.addEventListener("click", () => goToStep(1));
    }
    if (els.step2Next) {
      els.step2Next.addEventListener("click", () => goToStep(3));
    }
    if (els.step3Back) {
      els.step3Back.addEventListener("click", () => goToStep(2));
    }
    if (els.step3Next) {
      els.step3Next.addEventListener("click", () => {
        if (els.reviewOpportunity && els.genOpportunity) {
          const idx = els.genOpportunity.selectedIndex;
          const txt = idx >= 0 ? els.genOpportunity.options[idx].text : "";
          els.reviewOpportunity.textContent = txt || state.opportunityLabel || "--";
        }
        renderStep4Preview();
        goToStep(4);
      });
    }
    if (els.step4Back) {
      els.step4Back.addEventListener("click", () => goToStep(3));
    }

    if (els.extractBtn) {
      els.extractBtn.addEventListener("click", () => extractRfp(state.upload?.id));
    }
    if (els.generateBtn) {
      els.generateBtn.addEventListener("click", generateDocuments);
    }

    // Tab navigation arrows
    const tabNavLeft = document.querySelector(".tab-nav-left");
    const tabNavRight = document.querySelector(".tab-nav-right");
    const tabsContainer = document.querySelector(".editor-tabs");
    const fullscreenBtn = document.querySelector(".tab-action");

    if (tabNavLeft) {
      tabNavLeft.addEventListener("click", () => scrollTabs("left"));
    }
    if (tabNavRight) {
      tabNavRight.addEventListener("click", () => scrollTabs("right"));
    }
    if (tabsContainer) {
      tabsContainer.addEventListener("scroll", updateTabNavArrows);
    }
    if (fullscreenBtn) {
      fullscreenBtn.addEventListener("click", toggleFullscreen);
    }
    window.addEventListener("resize", updateTabNavArrows);

    els.editorTabs.forEach((tab) => {
      tab.addEventListener("click", () => switchDocument(tab.dataset.doc));
    });

    if (els.editableContent) {
      let inputTimer;
      els.editableContent.addEventListener("input", () => {
        clearTimeout(inputTimer);
        inputTimer = setTimeout(() => {
          updatePreview();
          updateWordCount();
          state.documents[state.currentDoc] = sanitizeHtml(els.editableContent.innerHTML);
          handleStepAvailability();
          scheduleSave();
        }, 200);
      });
    }

    els.toolbarBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const format = btn.dataset.format;
        if (!format || !els.editableContent) return;
        els.editableContent.focus();
        let command = format;
        let value = null;
        if (format === "h1" || format === "h2" || format === "h3") {
          command = "formatBlock";
          value = format;
        } else if (format === "ul") {
          command = "insertUnorderedList";
        } else if (format === "ol") {
          command = "insertOrderedList";
        }
        document.execCommand(command, false, value);
        updatePreview();
        state.documents[state.currentDoc] = els.editableContent.innerHTML;
        scheduleSave();
      });
    });

    els.optionCards.forEach((card) => {
      card.addEventListener("click", () => {
        card.classList.toggle("selected");
        const input = card.querySelector("input");
        if (input) input.checked = card.classList.contains("selected");
      });
    });

    async function performAiAction(btn, action) {
      if (!btn) return;

      const content = els.editableContent?.innerHTML || "";
      if (!content.trim()) {
        showMessage("No content to " + action, "error");
        return;
      }

      const original = btn.innerHTML;
      setButtonLoading(btn, action === "improve" ? "Improving..." : action === "shorten" ? "Shortening..." : "Expanding...");

      [els.improveBtn, els.shortenBtn, els.expandBtn].forEach((b) => {
        if (b) b.disabled = true;
      });

      try {
        const res = await fetch(
          `/api/opportunities/${encodeURIComponent(state.opportunityId)}/refine`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": getCsrf(),
            },
            body: JSON.stringify({
              content: content,
              action: action,
              section_name: state.currentDoc || null,
            }),
          }
        );

        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || `${action} failed`);
        }

        const data = await res.json();

        if (els.editableContent && data.refined_content) {
          els.editableContent.innerHTML = data.refined_content;
          if (state.currentDoc) {
            state.documents[state.currentDoc] = data.refined_content;
          }
          renderDocuments();
          scheduleSave();
        }

        showSaveIndicator(action.charAt(0).toUpperCase() + action.slice(1) + "d");
      } catch (err) {
        console.error(`${action} error:`, err);
        showMessage(err.message || `Failed to ${action}`, "error");
      } finally {
        setButtonLoading(btn, null);
        btn.innerHTML = original;
        [els.improveBtn, els.shortenBtn, els.expandBtn].forEach((b) => {
          if (b) b.disabled = false;
        });
      }
    }

    if (els.improveBtn) {
      els.improveBtn.addEventListener("click", () => performAiAction(els.improveBtn, "improve"));
    }
    if (els.shortenBtn) {
      els.shortenBtn.addEventListener("click", () => performAiAction(els.shortenBtn, "shorten"));
    }
    if (els.expandBtn) {
      els.expandBtn.addEventListener("click", () => performAiAction(els.expandBtn, "expand"));
    }

    if (els.exportWord) {
      els.exportWord.addEventListener("click", () => exportDocument("docx"));
    }
    if (els.exportPdf) {
      els.exportPdf.addEventListener("click", () => exportDocument("pdf"));
    }
    if (els.startNew) {
      els.startNew.addEventListener("click", () => window.location.reload());
    }
    if (els.resumeLatest) {
      els.resumeLatest.addEventListener("click", loadLatestSession);
    }
    if (els.manualSave) {
      els.manualSave.addEventListener("click", () => saveSession(true));
    }
    if (els.manualSaveInline) {
      els.manualSaveInline.addEventListener("click", () => saveSession(true));
    }

    const saveToFolderBtn = document.getElementById("saveToFolder");
    if (saveToFolderBtn) {
      saveToFolderBtn.addEventListener("click", saveToRfpFolder);
    }

    const prevPageBtn = document.getElementById("prevPage");
    if (prevPageBtn) {
      prevPageBtn.addEventListener("click", () => setPreviewPage(previewPageIndex - 1));
    }
    const nextPageBtn = document.getElementById("nextPage");
    if (nextPageBtn) {
      nextPageBtn.addEventListener("click", () => setPreviewPage(previewPageIndex + 1));
    }

    if (els.openSessionPicker) {
      els.openSessionPicker.addEventListener("click", openSessionModal);
    }
    if (els.openSessionPickerTop) {
      els.openSessionPickerTop.addEventListener("click", openSessionModal);
    }
    if (els.closeSessionModal) {
      els.closeSessionModal.addEventListener("click", closeSessionModal);
    }
    if (els.sessionModalOverlay) {
      els.sessionModalOverlay.addEventListener("click", closeSessionModal);
    }
    if (els.newSessionBtn) {
      els.newSessionBtn.addEventListener("click", startNewSession);
    }
    if (els.sessionSelectAll) {
      els.sessionSelectAll.addEventListener("change", () => {
        const checkAll = els.sessionSelectAll.checked;
        const checkboxes = els.sessionList?.querySelectorAll(".session-checkbox") || [];
        checkboxes.forEach((cb) => {
          cb.checked = checkAll;
          const id = cb.dataset.selectId;
          if (!id) return;
          const strId = String(id);
          if (checkAll) {
            selectedSessionIds.add(strId);
          } else {
            selectedSessionIds.delete(strId);
          }
        });
        updateSelectionDisplay();
      });
    }
    if (els.bulkDeleteSessions) {
      els.bulkDeleteSessions.addEventListener("click", async () => {
        if (!selectedSessionIds.size) return;
        if (!confirm(`Delete ${selectedSessionIds.size} draft${selectedSessionIds.size > 1 ? "s" : ""}? This cannot be undone.`)) {
          return;
        }
        for (const id of Array.from(selectedSessionIds)) {
          await deleteSession(Number(id));
        }
        selectedSessionIds = new Set();
        fetchSavedSessions();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && els.sessionModal?.classList.contains("active")) {
        closeSessionModal();
      }
    });
  }

  async function init() {
    const root = document.querySelector("main.ai-tools-page");
    if (root) root.classList.remove("hidden");
    bindEvents();
    fetchTrackedOpportunities();
    const params = new URLSearchParams(window.location.search);
    const sessionParam = params.get("session");
    if (sessionParam) {
      await loadSession(parseInt(sessionParam, 10));
    } else {
      // Optionally load latest session on page load
      // await loadLatestSession();
    }
    updateCurrentSessionDisplay();
    handleStepAvailability();
    goToStep(state.currentStep || 1);
    setInterval(() => saveSession(false), 30000);
    window.addEventListener("beforeunload", () => {
      const payload = buildSessionState();
      if (
        !payload.opportunityId &&
        !(payload.documents?.cover && payload.documents.cover.trim()) &&
        !(payload.documents?.responses && payload.documents.responses.trim())
      ) {
        return;
      }
      const body = JSON.stringify({
        session_id: state.sessionId,
        opportunity_id: payload.opportunityId,
        name: payload.opportunityLabel || null,
        state: payload,
      });
      fetch("/api/ai-sessions/save", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrf(),
        },
        body,
        keepalive: true,
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
