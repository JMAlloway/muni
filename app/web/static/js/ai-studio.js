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
    allowAugment: false,
    isExtracting: false,
  };

  let saveTimer = null;
  let augmentingExtraction = false;
  const MAX_UPLOAD_MB = 25;
  const allowedTypes = [".pdf", ".doc", ".docx", ".txt"];

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
      const hasContent = Boolean(
        (state.documents.cover && state.documents.cover.trim()) ||
          (state.documents.responses && state.documents.responses.trim())
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
      const timeout = setTimeout(() => controller.abort(), 30000);
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
      showMessage(err.message || "Extraction failed.", "error");
      if (els.extractStatus) {
        els.extractStatus.classList.remove("hidden");
        els.extractStatus.textContent = err.message || "Extraction failed.";
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

      const narratives = extracted.narrative_sections || [];
      const narrativeNames = narratives
        .map((n) => (typeof n === "string" ? n : n.name))
        .filter(Boolean);

      const forms = extracted.attachments_forms || [];
      const otherForms = extracted.required_forms || [];
      const allForms = [...new Set([...forms, ...otherForms])];

      if (narrativeNames.length) {
        const aiHeader = document.createElement("li");
        aiHeader.className = "checklist-header";
        aiHeader.innerHTML = "<strong>📝 AI Will Generate:</strong>";
        els.checklistItems.appendChild(aiHeader);

        narrativeNames.forEach((item) => {
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

      if (!narrativeNames.length && !allForms.length) {
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
              &#128203; <div><strong>Project Response</strong><span>Based on RFP requirements</span></div>
            </div>
          </div>
          <div class="section-instructions">
            <input type="text" class="section-instruction-input" data-section="project_response"
                   placeholder="Add specific context for this section (optional)">
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
      const shortReq = requirements.length > 80 ? `${requirements.substring(0, 77)}...` : requirements;
      const icon = index % 2 === 0 ? "&#128203;" : "&#128196;";
      const sectionKey = name.toLowerCase().replace(/[^a-z0-9]+/g, "_");

      html += `
        <div class="generate-option selected" data-section="${name}">
          <div class="option-header">
            <input type="checkbox" checked>
            <div class="option-content">
              ${icon} <div><strong>${name}</strong><span>${shortReq || "Required narrative section"}</span></div>
            </div>
          </div>
          <div class="section-instructions">
            <input type="text" class="section-instruction-input" data-section="${sectionKey}"
                   placeholder="Add specific details for this section (e.g., pricing, personnel names)">
          </div>
        </div>
      `;
    });

    els.generateOptions.innerHTML = html;
    bindOptionCardEvents();
  }

  function bindOptionCardEvents() {
    if (!els.generateOptions) return;

    els.generateOptions.querySelectorAll(".generate-option").forEach((card) => {
      const header = card.querySelector(".option-header") || card;
      const checkbox = card.querySelector("input[type='checkbox']");

      header.addEventListener("click", (e) => {
        if (e.target.classList.contains("section-instruction-input")) return;
        card.classList.toggle("selected");
        if (checkbox) checkbox.checked = card.classList.contains("selected");
      });
    });

    els.generateOptions.querySelectorAll(".section-instruction-input").forEach((input) => {
      input.addEventListener("click", (e) => e.stopPropagation());
    });
  }

  function getSectionInstructions() {
    const instructions = {};
    if (!els.generateOptions) return instructions;
    els.generateOptions.querySelectorAll(".section-instruction-input").forEach((input) => {
      const section = input.dataset.section;
      const value = input.value.trim();
      if (section && value) {
        instructions[section] = value;
      }
    });
    return instructions;
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
        instruction_upload_ids: state.upload?.id ? [state.upload.id] : [],
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
      const key = section.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
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
      state.currentDoc = state.responseSections[0].toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
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
        instruction_upload_ids: state.upload?.id ? [state.upload.id] : [],
      };
      if (els.customInstructions && els.customInstructions.value.trim()) {
        payload.custom_instructions = els.customInstructions.value.trim();
      }
      const sectionInstructions = getSectionInstructions();
      if (Object.keys(sectionInstructions).length > 0) {
        payload.section_instructions = sectionInstructions;
      }
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
        const normKey = key.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
        state.documents[normKey] = typeof value === "string" ? value : formatSoqText(value);
      });

      // Also map using exact section names from extraction if available
      state.responseSections.forEach((sectionName) => {
        const normKey = sectionName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
        if (!state.documents[normKey] && responseSections[sectionName]) {
          const value = responseSections[sectionName];
          state.documents[normKey] = typeof value === "string" ? value : formatSoqText(value);
        }
      });

      state.currentDoc = state.responseSections.length
        ? state.responseSections[0].toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")
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
    return {
      opportunityId: state.opportunityId,
      opportunityLabel: state.opportunityLabel,
      upload: state.upload,
      extracted: state.extracted,
      documents: state.documents,
      currentDoc: state.currentDoc,
      notes: els.customInstructions?.value || "",
    };
  }

  async function saveSession(manual = false) {
    const payload = buildSessionState();
    if (!payload.opportunityId && !payload.documents.cover && !payload.documents.responses) {
      return;
    }
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
      if (!res.ok) throw new Error("Save failed");
      const data = await res.json();
      state.sessionId = data.session_id;
      if (manual) {
        showSaveIndicator("Saved");
      } else {
        showSaveIndicator("Autosaved");
      }
    } catch (err) {
      showSaveIndicator(err.message || "Save failed", true);
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
      if (state.documents && !state.documents.responses && state.documents.soq) {
        state.documents.responses = state.documents.soq;
      }
      state.currentDoc = st.currentDoc || "cover";
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
      if (state.documents) {
        renderDocuments();
      }
      const hasDocs = Boolean(
        (state.documents?.cover && state.documents.cover.trim()) ||
          (state.documents?.responses && state.documents.responses.trim())
      );
      const targetStep = hasDocs ? 3 : state.extracted ? 2 : state.upload ? 1 : 1;
      goToStep(targetStep);
      handleStepAvailability();
      showMessage("Session restored.", "success");
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

    function simulateAiAction(btn) {
      if (!btn) return;
      const original = btn.innerHTML;
      setButtonLoading(btn, "Working...");
      setTimeout(() => {
        setButtonLoading(btn, null);
        btn.innerHTML = original;
        showSaveIndicator("Updated");
      }, 1200);
    }

    if (els.improveBtn) {
      els.improveBtn.addEventListener("click", () => simulateAiAction(els.improveBtn));
    }
    if (els.shortenBtn) {
      els.shortenBtn.addEventListener("click", () => simulateAiAction(els.shortenBtn));
    }
    if (els.expandBtn) {
      els.expandBtn.addEventListener("click", () => simulateAiAction(els.expandBtn));
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
  }

  async function init() {
    const root = document.querySelector("main.ai-tools-page");
    if (root) root.classList.remove("hidden");
    bindEvents();
    fetchTrackedOpportunities();
    const params = new URLSearchParams(window.location.search);
    const sessionParam = params.get("session");
    if (sessionParam) {
      await loadSession(sessionParam);
    }
    handleStepAvailability();
    goToStep(1);
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
