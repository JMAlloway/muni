# Session Management Implementation Guide

## Current Status

### Already Implemented (Backend)
| Feature | Endpoint | Status |
|---------|----------|--------|
| Save session | `POST /api/ai-sessions/save` | ✅ Working |
| Load session | `GET /api/ai-sessions/{id}` | ✅ Working |
| List recent sessions | `GET /api/ai-sessions/recent` | ✅ Working |
| Delete session | `DELETE /api/ai-sessions/{id}` | ✅ Working |
| Auto-save (800ms debounce) | Frontend | ✅ Working |
| Load last session | Button exists | ✅ Working |

### What's Missing (UI)
| Feature | Status |
|---------|--------|
| Session browser/picker modal | ❌ Not implemented |
| Session list in Step 3 | ❌ Not implemented |
| Session rename UI | ❌ Not implemented |
| Session delete confirmation | ❌ Not implemented |

---

## Implementation Plan

### Goal
Allow users to:
1. See all their saved sessions for an opportunity
2. Click to load any previous session
3. Delete sessions they no longer need
4. Clear visual indication of which session is active

---

## Part 1: Add Session Picker UI

### File: `app/api/ai_tools.py`

Add a "Saved Drafts" dropdown/panel in the Step 3 header area.

**Find the step3 section (around line 158)** and add a session picker:

```html
<!-- Add after the step3 header, before editor-tabs -->
<div class="session-picker-bar">
  <div class="session-info">
    <span class="session-label">Current Draft:</span>
    <span class="session-name" id="currentSessionName">Unsaved</span>
    <span class="session-time" id="currentSessionTime"></span>
  </div>
  <div class="session-actions">
    <button type="button" class="session-btn" id="openSessionPicker">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
      </svg>
      Saved Drafts
    </button>
    <button type="button" class="session-btn secondary" id="newSessionBtn">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
      New Draft
    </button>
  </div>
</div>
```

**Add the session picker modal (before closing </main> tag):**

```html
<!-- Session Picker Modal -->
<div class="session-modal-overlay" id="sessionModalOverlay"></div>
<div class="session-modal" id="sessionModal">
  <div class="session-modal-header">
    <h3>Saved Drafts</h3>
    <button type="button" class="session-modal-close" id="closeSessionModal">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>
  </div>
  <div class="session-modal-body">
    <div class="session-list" id="sessionList">
      <!-- Sessions will be populated by JavaScript -->
      <div class="session-loading">Loading saved drafts...</div>
    </div>
  </div>
  <div class="session-modal-footer">
    <span class="session-count" id="sessionCount">0 saved drafts</span>
  </div>
</div>
```

---

## Part 2: Add CSS for Session Picker

### File: `app/web/static/css/ai-studio.css`

Add these styles at the end of the file:

```css
/* ===== SESSION PICKER BAR ===== */
.ai-tools-page .session-picker-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-bottom: 1px solid #d1fae5;
  gap: 16px;
}

.ai-tools-page .session-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ai-tools-page .session-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ai-tools-page .session-name {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.ai-tools-page .session-time {
  font-size: 12px;
  color: #94a3b8;
}

.ai-tools-page .session-actions {
  display: flex;
  gap: 8px;
}

.ai-tools-page .session-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ai-tools-page .session-btn:hover {
  background: #f8fafc;
  border-color: #16a34a;
  color: #16a34a;
}

.ai-tools-page .session-btn.secondary {
  background: transparent;
  border-color: transparent;
}

.ai-tools-page .session-btn.secondary:hover {
  background: #f0fdf4;
}

/* ===== SESSION MODAL ===== */
.ai-tools-page .session-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
  z-index: 9998;
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
}

.ai-tools-page .session-modal-overlay.active {
  opacity: 1;
  visibility: visible;
}

.ai-tools-page .session-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(0.95);
  width: 560px;
  max-width: 90vw;
  max-height: 80vh;
  background: #ffffff;
  border-radius: 16px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  opacity: 0;
  visibility: hidden;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.ai-tools-page .session-modal.active {
  opacity: 1;
  visibility: visible;
  transform: translate(-50%, -50%) scale(1);
}

.ai-tools-page .session-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e2e8f0;
}

.ai-tools-page .session-modal-header h3 {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}

.ai-tools-page .session-modal-close {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: #64748b;
  transition: all 0.15s ease;
}

.ai-tools-page .session-modal-close:hover {
  background: #fee2e2;
  color: #dc2626;
}

.ai-tools-page .session-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.ai-tools-page .session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-tools-page .session-loading {
  text-align: center;
  padding: 40px;
  color: #94a3b8;
}

.ai-tools-page .session-empty {
  text-align: center;
  padding: 40px;
  color: #94a3b8;
}

.ai-tools-page .session-empty svg {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

/* Session Item Card */
.ai-tools-page .session-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ai-tools-page .session-item:hover {
  background: #f0fdf4;
  border-color: #86efac;
  transform: translateX(4px);
}

.ai-tools-page .session-item.active {
  background: #ecfdf5;
  border-color: #16a34a;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.1);
}

.ai-tools-page .session-item-icon {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #16a34a, #22c55e);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 20px;
  flex-shrink: 0;
}

.ai-tools-page .session-item-content {
  flex: 1;
  min-width: 0;
}

.ai-tools-page .session-item-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ai-tools-page .session-item-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
}

.ai-tools-page .session-item-progress {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ai-tools-page .session-progress-bar {
  width: 60px;
  height: 4px;
  background: #e2e8f0;
  border-radius: 2px;
  overflow: hidden;
}

.ai-tools-page .session-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #16a34a, #22c55e);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.ai-tools-page .session-item-actions {
  display: flex;
  gap: 4px;
}

.ai-tools-page .session-action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: #94a3b8;
  transition: all 0.15s ease;
}

.ai-tools-page .session-action-btn:hover {
  background: #f1f5f9;
  color: #475569;
}

.ai-tools-page .session-action-btn.delete:hover {
  background: #fee2e2;
  color: #dc2626;
}

.ai-tools-page .session-modal-footer {
  padding: 16px 24px;
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 0 0 16px 16px;
}

.ai-tools-page .session-count {
  font-size: 13px;
  color: #64748b;
}
```

---

## Part 3: Add JavaScript for Session Management

### File: `app/web/static/js/ai-studio.js`

**Add these element references in the `els` object (around line 30):**

```javascript
// Session picker elements
sessionModalOverlay: document.getElementById("sessionModalOverlay"),
sessionModal: document.getElementById("sessionModal"),
sessionList: document.getElementById("sessionList"),
sessionCount: document.getElementById("sessionCount"),
openSessionPicker: document.getElementById("openSessionPicker"),
closeSessionModal: document.getElementById("closeSessionModal"),
newSessionBtn: document.getElementById("newSessionBtn"),
currentSessionName: document.getElementById("currentSessionName"),
currentSessionTime: document.getElementById("currentSessionTime"),
```

**Add session management functions (after `loadLatestSession` around line 1222):**

```javascript
// ============================================
// SESSION PICKER FUNCTIONALITY
// ============================================

function openSessionModal() {
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

  try {
    const res = await fetch("/api/ai-sessions/recent?limit=50", {
      credentials: "include",
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

  // Filter to current opportunity if one is selected
  let filtered = sessions;
  if (state.opportunityId) {
    filtered = sessions.filter(s => s.opportunity_id === state.opportunityId);
  }

  if (filtered.length === 0) {
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

  const html = filtered.map(session => {
    const isActive = state.sessionId === session.id;
    const progress = session.sections_total > 0
      ? Math.round((session.sections_completed / session.sections_total) * 100)
      : 0;
    const updatedAt = formatRelativeTime(session.updated_at);
    const title = session.name || session.opportunity_title || "Untitled Draft";

    return `
      <div class="session-item ${isActive ? 'active' : ''}" data-session-id="${session.id}">
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
          <button type="button" class="session-action-btn delete" data-delete-id="${session.id}" title="Delete draft">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    `;
  }).join("");

  els.sessionList.innerHTML = html;
  updateSessionCount(filtered.length);

  // Add click handlers
  els.sessionList.querySelectorAll(".session-item").forEach(item => {
    item.addEventListener("click", (e) => {
      // Don't trigger if clicking delete button
      if (e.target.closest(".session-action-btn")) return;

      const sessionId = item.dataset.sessionId;
      if (sessionId) {
        loadSession(parseInt(sessionId, 10));
        closeSessionModal();
      }
    });
  });

  // Add delete handlers
  els.sessionList.querySelectorAll("[data-delete-id]").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const sessionId = btn.dataset.deleteId;
      if (confirm("Delete this draft? This cannot be undone.")) {
        await deleteSession(parseInt(sessionId, 10));
        fetchSavedSessions(); // Refresh list
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

    // If we deleted the current session, clear state
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

  // Clear session state but keep opportunity
  state.sessionId = null;
  state.documents = {};
  state.responseSections = [];
  state.currentDoc = "";

  // Clear editor
  if (els.editableContent) {
    els.editableContent.innerHTML = "";
  }
  if (els.previewContent) {
    els.previewContent.innerHTML = "";
  }

  // Clear tabs
  renderDocumentTabs();
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
    els.sessionCount.textContent = `${count} saved draft${count !== 1 ? 's' : ''}`;
  }
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
```

**Add event listeners in `bindEvents()` (around line 1454):**

```javascript
// Session picker events
if (els.openSessionPicker) {
  els.openSessionPicker.addEventListener("click", openSessionModal);
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

// Close modal on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && els.sessionModal?.classList.contains("active")) {
    closeSessionModal();
  }
});
```

**Update `saveSession()` function to update display (around line 1150):**

After the successful save, add:
```javascript
// After: state.sessionId = data.session_id || data.id || state.sessionId;
updateCurrentSessionDisplay();
```

**Update `loadSession()` function to update display (around line 1200):**

At the end of successful load, add:
```javascript
updateCurrentSessionDisplay();
```

---

## Part 4: Update Load on Page Init

**In the init function or DOMContentLoaded handler:**

```javascript
// Check for session_id URL parameter to load specific session
const urlParams = new URLSearchParams(window.location.search);
const sessionIdParam = urlParams.get("session");
if (sessionIdParam) {
  loadSession(parseInt(sessionIdParam, 10));
} else {
  // Optionally load latest session on page load
  // loadLatestSession();
}

// Initialize session display
updateCurrentSessionDisplay();
```

---

## Summary

### Files to Modify:

| File | Changes |
|------|---------|
| `app/api/ai_tools.py` | Add session picker bar HTML + modal HTML |
| `app/web/static/css/ai-studio.css` | Add ~200 lines of session picker CSS |
| `app/web/static/js/ai-studio.js` | Add ~180 lines of session management JS |

### User Flow After Implementation:

1. User edits content → **Auto-saves every 800ms**
2. User clicks "Saved Drafts" button → **Modal shows all drafts**
3. User clicks a draft → **Loads that session state**
4. User clicks delete → **Removes draft after confirmation**
5. User clicks "New Draft" → **Starts fresh (old work saved)**
6. User leaves and returns → **Can load any previous draft**

### What Gets Saved:
- All generated document content (HTML)
- Current active tab/section
- RFP extraction data
- Custom instructions
- Upload reference
- Progress metrics

### Already Working (No Changes Needed):
- Auto-save backend (`POST /api/ai-sessions/save`)
- Load backend (`GET /api/ai-sessions/{id}`)
- List backend (`GET /api/ai-sessions/recent`)
- Delete backend (`DELETE /api/ai-sessions/{id}`)
- CSRF protection
- User authorization
