(function () {
  const getCsrf = () => {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? match[1] : "";
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
    editorTabs: document.querySelectorAll(".editor-tab"),
    toolbarBtns: document.querySelectorAll(".toolbar-btn"),
    optionCards: document.querySelectorAll(".generate-option"),
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
    documents: { cover: "", responses: "" },
    currentDoc: "cover",
    sessionId: null,
  };

  let saveTimer = null;

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

  async function fetchTrackedOpportunities() {
    const select = els.genOpportunity;
    if (!select) return;
    select.innerHTML = `<option value="">Loading tracked opportunities...</option>`;
    try {
      const res = await fetch("/api/tracked/my", { credentials: "include" });
      if (!res.ok) throw new Error(`Unable to load tracked (${res.status})`);
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
      showMessage("Could not load tracked opportunities. Try refreshing.", "error");
    }
  }

  async function uploadFile(file) {
    if (!state.opportunityId) {
      showMessage("Select an opportunity before uploading.", "error");
      return null;
    }
    if (!file) return null;
    const fd = new FormData();
    fd.append("opportunity_id", state.opportunityId);
    fd.append("files", file, file.name);
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
    clearMessage();
    setButtonLoading(els.extractBtn, "Analyzing RFP...");
    try {
      const res = await fetch(`/api/rfp-extract/${uploadId}`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Extraction failed (${res.status})`);
      }
      const data = await res.json();
      state.extracted = data;
      renderExtraction();
      await fetchOpportunityExtraction();
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
    }
  }

  function renderExtraction() {
    if (!els.extractResults) return;
    const root = state.extracted || {};
    const extracted = root.extracted || root.discovery || root || {};
    if (!extracted || Object.keys(extracted).length === 0) {
      if (els.extractStatus) {
        els.extractStatus.classList.remove("hidden");
        els.extractStatus.textContent = "No extraction results yet. Try running extraction again.";
      }
      els.extractResults.classList.add("hidden");
      return;
    }
    const summary =
      extracted.summary ||
      extracted.scope_of_work ||
      (root.discovery && root.discovery.summary) ||
      root.summary ||
      "No summary available yet.";
    const checklist = []
      .concat(extracted.required_documents || [])
      .concat(extracted.required_forms || [])
      .concat(extracted.checklist || [])
      .concat(extracted.compliance_terms || [])
      .concat((root.discovery && root.discovery.requirements) || [])
      .filter(Boolean);

    const dates =
      extracted.key_dates ||
      extracted.timeline ||
      (root.discovery && (root.discovery.key_dates || root.discovery.timeline)) ||
      [];

    if (els.summaryText) els.summaryText.textContent = summary;

    if (els.checklistItems) {
      els.checklistItems.innerHTML = "";
      if (!checklist.length) {
        els.checklistItems.innerHTML = `<li>No checklist items detected yet.</li>`;
      } else {
        checklist.slice(0, 12).forEach((item) => {
          const li = document.createElement("li");
          li.textContent = item;
          els.checklistItems.appendChild(li);
        });
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
      } else if (data.due_date) {
        els.keyDates.textContent = `Due date: ${data.due_date}`;
      } else {
        els.keyDates.textContent = "No key dates captured.";
      }
    }

    els.extractResults.classList.remove("hidden");
    const isEmpty =
      (!summary || summary.toLowerCase().includes("no summary")) &&
      (!checklist.length) &&
      (!dates || !dates.length);
    if (els.extractStatus) {
      if (isEmpty) {
        els.extractStatus.classList.remove("hidden");
        els.extractStatus.textContent =
          "Extraction returned no summary/checklist/dates. Try rerunning or check the uploaded file.";
      } else {
        els.extractStatus.classList.add("hidden");
        els.extractStatus.textContent = "";
      }
    }
    handleStepAvailability();
  }

  async function fetchOpportunityExtraction() {
    if (!state.opportunityId) return;
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(state.opportunityId)}/extracted`, {
        credentials: "include",
      });
      if (!res.ok) return;
      const data = await res.json();
      state.extracted = data;
      renderExtraction();
      handleStepAvailability();
    } catch (err) {
      showMessage(err.message || "Could not load extracted data.", "error");
    }
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
    const content = state.documents[state.currentDoc] || "";
    els.editableContent.innerHTML = content;
    updatePreview();
    updateWordCount();
    els.editorTabs.forEach((tab) => {
      const doc = tab.dataset.doc;
      tab.classList.toggle("active", doc === state.currentDoc);
    });
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
      state.documents.cover = docs.cover_letter || "";
      state.documents.responses = formatSoqText(docs.soq);
      state.currentDoc = "cover";
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
    els.previewContent.innerHTML = els.editableContent.innerHTML;
  }

  function updateWordCount() {
    if (!els.editableContent || !els.wordCount) return;
    const text = (els.editableContent.innerText || "").trim();
    const words = text ? text.split(/\s+/).filter(Boolean).length : 0;
    els.wordCount.textContent = `${words} word${words === 1 ? "" : "s"}`;
  }

  function switchDocument(doc) {
    if (!doc) return;
    state.documents[state.currentDoc] = els.editableContent?.innerHTML || "";
    state.currentDoc = doc;
    renderDocuments();
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
        state.extracted = null;
        if (els.extractResults) els.extractResults.classList.add("hidden");
        handleStepAvailability();
        fetchOpportunityExtraction();
        scheduleSave();
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
        if (els.uploadedFile) els.uploadedFile.classList.add("hidden");
        if (els.uploadArea) els.uploadArea.style.display = "block";
        if (els.rfpUploadInput) els.rfpUploadInput.value = "";
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
      els.editableContent.addEventListener("input", () => {
        updatePreview();
        updateWordCount();
        state.documents[state.currentDoc] = els.editableContent.innerHTML;
        handleStepAvailability();
        scheduleSave();
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
