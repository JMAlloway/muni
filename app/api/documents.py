from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.api._layout import page_shell
from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.storage import create_presigned_get

router = APIRouter(tags=["documents"])

STATIC_VER = "20251127.3"


@router.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request):
    """
    Documents page wired to real uploads (mirrors Homepage_test/documetns.html styling).
    """
    user_email = get_current_user_email(request)
    body = """
<link rel="stylesheet" href="/static/css/dashboard.css">
<link rel="stylesheet" href="/static/css/documents.css">

<main class="page documents-page">
  <div class="documents-header fade-in">
    <div class="documents-title-section">
      <h1 class="documents-title">Documents</h1>
      <p class="documents-subtitle">Manage your bid documents, proposals, and templates</p>
    </div>
    <div class="documents-actions">
      <div class="select-and-hint">
        <label class="folder-select">
          <span>Select a folder to enable upload</span>
          <select id="uploadOpportunity">
            <option value="">Select folder</option>
          </select>
        </label>
      </div>
      <button class="upload-btn" id="uploadTrigger" type="button" disabled>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        Upload
      </button>
      <button class="new-folder-btn" id="newFolderBtn" type="button">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          <line x1="12" y1="11" x2="12" y2="17"/>
          <line x1="9" y1="14" x2="15" y2="14"/>
        </svg>
        New Folder
      </button>
      <input type="file" id="uploadInput" multiple style="display:none;" />
    </div>
  </div>

  <div class="documents-toolbar fade-in stagger-1">
    <div class="search-box">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <input type="text" placeholder="Search documents..." id="searchInput">
    </div>
    <div class="toolbar-right">
      <button class="select-mode-btn" id="selectModeBtn" type="button">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 11l3 3L22 4"/>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>
        Select
      </button>
      <div class="filter-group">
        <button class="filter-btn active" data-filter="all">All</button>
        <button class="filter-btn" data-filter="proposals">Proposals</button>
        <button class="filter-btn" data-filter="templates">Templates</button>
        <button class="filter-btn" data-filter="contracts">Contracts</button>
      </div>
      <div class="view-toggle">
        <button class="view-btn active" data-view="grid" title="Grid View">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7"/>
            <rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/>
          </svg>
        </button>
        <button class="view-btn" data-view="list" title="List View">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="8" y1="6" x2="21" y2="6"/>
            <line x1="8" y1="12" x2="21" y2="12"/>
            <line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/>
            <line x1="3" y1="12" x2="3.01" y2="12"/>
            <line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
  </div>

  <div class="folders-section fade-in stagger-2">
    <h3 class="section-label">Folders</h3>
    <div class="folders-grid" id="foldersGrid"></div>
    <div class="subfolders-grid" id="subfolderGrid"></div>
  </div>

  <div class="files-section fade-in stagger-3">
    <div class="section-header">
      <h3 class="section-label">Recent Documents</h3>
      <div class="bulk-actions" id="bulkActions" style="display:none;">
        <label class="select-all">
          <input type="checkbox" id="selectAllFiles"> Select all
        </label>
        <span class="selected-count" id="selectedCount">0 selected</span>
        <button class="bulk-delete-btn" id="bulkDeleteBtn" disabled title="Delete selected files">
          Delete selected
        </button>
      </div>
      <span class="file-count" id="fileCount">Loading...</span>
    </div>
    <div class="files-grid grid-view" id="filesGrid"></div>
  </div>
</main>

<!-- Floating selection bar -->
<div class="selection-bar" id="selectionBar">
  <div class="selection-bar-content">
    <button class="selection-cancel-btn" id="cancelSelectionBtn" type="button">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
      Cancel
    </button>
    <div class="selection-info">
      <span class="selection-count" id="selectionCount">0 selected</span>
      <button class="select-all-btn" id="selectAllBtn" type="button">Select all</button>
    </div>
    <button class="delete-selected-btn" id="deleteSelectedBtn" type="button" disabled>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
      </svg>
      Delete <span id="deleteCount"></span>
    </button>
  </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {
  const state = {
    filter: 'all',
    folder: null,
    search: '',
    view: 'grid',
    selectionMode: false,
    selectedIds: new Set(),
    isUploading: false
  };
  const filterBtns = document.querySelectorAll('.filter-btn');
  const viewBtns = document.querySelectorAll('.view-btn');
  const searchInput = document.getElementById('searchInput');
  const uploadInput = document.getElementById('uploadInput');
  const uploadTrigger = document.getElementById('uploadTrigger');
  const uploadSelect = document.getElementById('uploadOpportunity');
  const newFolderBtn = document.getElementById('newFolderBtn');
  const foldersGrid = document.getElementById('foldersGrid');
  const filesGrid = document.getElementById('filesGrid');
  const fileCountEl = document.getElementById('fileCount');
  const subfolderGrid = document.getElementById('subfolderGrid');
  const selectModeBtn = document.getElementById('selectModeBtn');
  const selectionBar = document.getElementById('selectionBar');
  const selectionCount = document.getElementById('selectionCount');
  const selectAllBtn = document.getElementById('selectAllBtn');
  const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
  const cancelSelectionBtn = document.getElementById('cancelSelectionBtn');
  const deleteCount = document.getElementById('deleteCount');
  const selectAllFiles = document.getElementById('selectAllFiles');
  const selectedCountEl = document.getElementById('selectedCount');
  const bulkActions = document.getElementById('bulkActions');
  const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
  let allFiles = [];
  let foldersData = [];
  let oppSelectOptions = [];

  function getCsrf() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match && match[1] ? match[1] : '';
  }

  init();

  async function init() {
    attachHandlers();
    await refreshFiles();
  }

  function attachHandlers() {
    filterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.filter = btn.dataset.filter || 'all';
        applyFilters();
      });
    });

    viewBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        viewBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.view = btn.dataset.view || 'grid';
        filesGrid.classList.remove('grid-view', 'list-view');
        filesGrid.classList.add(state.view + '-view');
      });
    });

    searchInput.addEventListener('input', () => {
      state.search = (searchInput.value || '').toLowerCase();
      applyFilters();
    });

    if (uploadTrigger && uploadInput) {
      uploadTrigger.addEventListener('click', () => uploadInput.click());
      uploadInput.addEventListener('change', handleUpload);
    }

    if (uploadSelect) {
      uploadSelect.addEventListener('change', () => {
        const hasFolder = !!uploadSelect.value;
        if (uploadTrigger) uploadTrigger.disabled = !hasFolder;
      });
    }

    if (newFolderBtn) {
      newFolderBtn.addEventListener('click', () => {
        alert('Folders are created from opportunities you track. Go to your opportunities dashboard and add/track an opportunity to create a folder here.');
        window.location.href = '/opportunities';
      });
    }

    if (selectAllFiles) {
      selectAllFiles.addEventListener('change', () => {
        selectAllVisible(selectAllFiles.checked);
      });
    }

    if (bulkDeleteBtn) {
      bulkDeleteBtn.addEventListener('click', () => {
        handleBulkDelete();
      });
    }

    if (selectModeBtn) {
      selectModeBtn.addEventListener('click', toggleSelectionMode);
    }

    if (cancelSelectionBtn) {
      cancelSelectionBtn.addEventListener('click', () => toggleSelectionMode(false));
    }

    if (selectAllBtn) {
      selectAllBtn.addEventListener('click', selectAllVisible);
    }

    if (deleteSelectedBtn) {
      deleteSelectedBtn.addEventListener('click', handleBulkDelete);
    }
  }

  async function refreshFiles() {
    try {
      const res = await fetch('/documents/data', { credentials: 'include' });
      if (!res.ok) throw new Error('Failed to load documents');
      const data = await res.json();
      foldersData = data.folders || [];
      oppSelectOptions = data.opportunities || [];
      renderFolders(foldersData);
      renderUploadSelect(oppSelectOptions);
      renderFiles(data.files || []);
    } catch (err) {
      console.error(err);
      if (fileCountEl) fileCountEl.textContent = 'Unable to load documents';
    }
  }

  function renderUploadSelect(opps) {
    uploadSelect.innerHTML = '<option value=\"\">Select folder</option>';
    if (!opps.length) {
      uploadSelect.disabled = true;
      if (uploadTrigger) uploadTrigger.disabled = true;
      return;
    }
    uploadSelect.disabled = false;
    if (uploadTrigger) uploadTrigger.disabled = true; // until selection
    opps.forEach(o => {
      const opt = document.createElement('option');
      opt.value = o.id;
      opt.textContent = o.title || `Opportunity ${o.id}`;
      uploadSelect.appendChild(opt);
    });
  }

  function renderFolders(list) {
    foldersGrid.innerHTML = '';
    const fallback = [
      { id: 'active', title: 'Active Bids', count: 0 },
      { id: 'archive', title: 'Archive', count: 0 },
    ];
    const folders = (list && list.length) ? list : fallback;
    folders.forEach(f => {
      const card = document.createElement('div');
      card.className = 'folder-card';
      card.dataset.folder = f.id;
      card.innerHTML = `
        <div class="folder-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div class="folder-info">
          <div class="folder-name">${f.title || 'Folder'}</div>
          <div class="folder-count">${(f.count || 0)} files</div>
        </div>`;
      card.addEventListener('click', () => {
        state.folder = f.id;
        renderSubfolders(f.id);
        applyFilters();
      });
      foldersGrid.appendChild(card);
    });
    renderSubfolders(null);
  }

  function updateBulkUI() {
    const count = state.selectedIds.size;
    if (selectionCount) {
      selectionCount.textContent = `${count} selected`;
    }
    if (deleteCount) {
      deleteCount.textContent = count ? count : '';
    }
    if (deleteSelectedBtn) {
      deleteSelectedBtn.disabled = count === 0;
    }

    const visibleCards = Array.from(document.querySelectorAll('.file-card')).filter(card => card.style.display !== 'none');
    const allVisibleSelected = visibleCards.length > 0 && visibleCards.every(card => state.selectedIds.has(String(card.dataset.fileId || '')));
    if (selectAllBtn) {
      selectAllBtn.textContent = allVisibleSelected ? 'Clear selection' : 'Select all';
      selectAllBtn.disabled = visibleCards.length === 0;
    }

    if (selectionBar) {
      selectionBar.classList.toggle('visible', state.selectionMode);
    }
    if (selectModeBtn) {
      selectModeBtn.classList.toggle('active', state.selectionMode);
    }

    // Hide legacy bulk actions
    if (bulkActions) {
      bulkActions.style.display = 'none';
    }
    if (selectedCountEl) {
      selectedCountEl.textContent = `${count} selected`;
    }
    if (bulkDeleteBtn) {
      bulkDeleteBtn.disabled = true;
    }
    if (selectAllFiles) {
      selectAllFiles.checked = false;
      selectAllFiles.indeterminate = false;
    }

    if (filesGrid) {
      filesGrid.classList.toggle('selection-mode-active', state.selectionMode);
    }
    document.querySelectorAll('.file-card').forEach(card => {
      const cardId = String(card.dataset.fileId || '');
      card.classList.toggle('selected', state.selectedIds.has(cardId));
    });
  }

  function renderSubfolders(folderId) {
    subfolderGrid.innerHTML = '';
    let subset = [];
    if (folderId === 'archive') {
      subset = oppSelectOptions.filter(o => (o.status || '').includes('archive'));
    } else if (folderId === 'active') {
      subset = oppSelectOptions.filter(o => !(o.status || '').includes('archive'));
    }
    if (!subset.length) return;
    subset.forEach(o => {
      const card = document.createElement('div');
      card.className = 'subfolder-card';
      card.dataset.opportunity = o.id;
      card.innerHTML = `
        <div class="subfolder-name ticker">
          <span>${o.title || 'Opportunity'}</span>
        </div>
        <div class="subfolder-count">${(o.count || 0)} files</div>
      `;
      card.addEventListener('click', () => {
        state.folder = 'active';
        state.search = '';
        searchInput.value = '';
        document.querySelectorAll('.file-card').forEach(f => {
          f.style.display = (f.dataset.opportunity === String(o.id)) ? 'flex' : 'none';
        });
        updateCountManual();
        updateBulkUI();
      });
      subfolderGrid.appendChild(card);
    });
  }

  function renderFiles(files) {
    allFiles = files || [];
    state.selectedIds.clear();
    state.selectionMode = false;
    filesGrid.innerHTML = '';
    allFiles.forEach(file => {
      const card = document.createElement('div');
      const cat = categoryFor(file);
      const ext = ((file.filename || '').split('.').pop() || '').toUpperCase() || 'FILE';
      const cls = pickPreviewClass(file.mime);
      card.className = 'file-card';
      card.dataset.fileId = file.id;
      card.dataset.category = cat;
      card.dataset.opportunity = file.opportunity_id || '';
      card.dataset.folder = file.folder || '';
      card.dataset.name = (file.filename || '').toLowerCase();
      card.innerHTML = `
        <div class="file-selection-overlay">
          <div class="file-selection-check">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
        </div>
        <div class="file-preview ${cls}">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          <span class="file-type-badge">${ext}</span>
        </div>
        <div class="file-info">
          <div class="file-name">${file.filename || 'Untitled'}</div>
          <div class="file-meta">
            <span>${file.size_label || ''}</span>
            <span class="meta-dot">&middot;</span>
            <span>${file.modified_label || ''}</span>
          </div>
        </div>
        <div class="file-actions">
          ${file.download_url ? `
            <a class="file-action-btn" title="Download" href="${file.download_url}" target="_blank" rel="noopener">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
            </a>
          ` : '<span class="file-action-btn" title="No download" style="opacity:0.5; cursor:not-allowed;">&mdash;</span>'}
          <button class="file-action-btn delete-btn" title="Delete" data-file-id="${file.id}" data-filename="${file.filename}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              <line x1="10" y1="11" x2="10" y2="17"/>
              <line x1="14" y1="11" x2="14" y2="17"/>
            </svg>
          </button>
        </div>
      `;

      filesGrid.appendChild(card);

      // Attach click handler for selection mode
      card.addEventListener('click', () => {
        if (state.selectionMode) {
          toggleFileSelection(file.id, card);
        }
      });

      // Attach individual delete handler
      const deleteBtn = card.querySelector('.delete-btn');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          handleDelete(file.id, file.filename);
        });
      }
    });
    applyFilters();
    updateBulkUI();
  }

  function categoryFor(file) {
    const name = (file.filename || '').toLowerCase();
    if (name.endsWith('.doc') || name.endsWith('.docx') || name.endsWith('.ppt') || name.endsWith('.pptx')) return 'proposals';
    if (name.endsWith('.xls') || name.endsWith('.xlsx') || name.includes('template')) return 'templates';
    if (name.includes('contract') || name.includes('nda')) return 'contracts';
    return 'all';
  }

  function pickPreviewClass(mime) {
    const m = (mime || '').toLowerCase();
    if (m.includes('pdf')) return 'pdf';
    if (m.includes('excel') || m.includes('spreadsheet')) return 'xlsx';
    if (m.includes('presentation')) return 'pptx';
    return 'docx';
  }

  function toggleSelectionMode(force) {
    const nextMode = typeof force === 'boolean' ? force : !state.selectionMode;
    state.selectionMode = nextMode;
    if (!state.selectionMode) {
      state.selectedIds.clear();
    }
    updateBulkUI();
  }

  function toggleFileSelection(fileId, card) {
    if (!state.selectionMode) return;
    const id = String(fileId);
    if (state.selectedIds.has(id)) {
      state.selectedIds.delete(id);
      if (card) card.classList.remove('selected');
    } else {
      state.selectedIds.add(id);
      if (card) card.classList.add('selected');
    }
    updateBulkUI();
  }

  function applyFilters() {
    const q = state.search;
    const cat = state.filter;
    const folder = state.folder ? String(state.folder) : null;
    let visible = 0;
    document.querySelectorAll('.file-card').forEach(card => {
      const matchesCat = (cat === 'all') || card.dataset.category === cat;
      const matchesFolder = (!folder) || card.dataset.folder === folder;
      const matchesSearch = (!q) || (card.dataset.name || '').includes(q);
      const show = matchesCat && matchesFolder && matchesSearch;
      card.style.display = show ? 'flex' : 'none';
      if (show) visible += 1;
    });
    if (fileCountEl) fileCountEl.textContent = `Showing ${visible} files`;
    updateBulkUI();
  }

  function updateCountManual() {
    let visible = 0;
    document.querySelectorAll('.file-card').forEach(card => {
      if (card.style.display !== 'none') visible += 1;
    });
    if (fileCountEl) fileCountEl.textContent = `Showing ${visible} files`;
  }

  function selectAllVisible(checked) {
    const visibleCards = Array.from(document.querySelectorAll('.file-card')).filter(card => card.style.display !== 'none');
    const shouldSelect = typeof checked === 'boolean'
      ? checked
      : !(visibleCards.length > 0 && visibleCards.every(card => state.selectedIds.has(String(card.dataset.fileId || ''))));

    visibleCards.forEach(card => {
      const id = String(card.dataset.fileId || '');
      if (!id) return;
      if (shouldSelect) {
        state.selectedIds.add(id);
        card.classList.add('selected');
      } else {
        state.selectedIds.delete(id);
        card.classList.remove('selected');
      }
    });

    if (shouldSelect && visibleCards.length) {
      state.selectionMode = true;
    }
    updateBulkUI();
  }

  async function handleUpload() {
    const oppId = uploadSelect.value;
    if (!oppId) { alert('Select a folder (opportunity) first.'); return; }
    if (!this.files || !this.files.length) return;

    if (state.isUploading) {
      console.log('Upload already in progress, ignoring duplicate request');
      return;
    }

    state.isUploading = true;
    const trigger = uploadTrigger;
    let originalHtml = '';
    if (trigger) {
      trigger.disabled = true;
      originalHtml = trigger.innerHTML;
      trigger.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinning">
          <circle cx="12" cy="12" r="10"></circle>
        </svg>
        Uploading...
      `;
    }

    const formData = new FormData();
    formData.append('opportunity_id', oppId);
    Array.from(this.files).forEach(f => formData.append('files', f));
    try {
      const res = await fetch('/uploads/add', {
        method: 'POST',
        body: formData,
        credentials: 'include',
        headers: { 'X-CSRF-Token': getCsrf() }
      });
      if (!res.ok) throw new Error('Upload failed');
      await refreshFiles();
      this.value = '';
    } catch(err) {
      alert('Upload failed. Please try again.');
      console.error(err);
    } finally {
      state.isUploading = false;
      if (trigger) {
        trigger.disabled = false;
        trigger.innerHTML = originalHtml || 'Upload';
      }
    }
  }
  async function handleDelete(fileId, filename) {
    if (!confirm(`Delete "${filename}"?\n\nThis action cannot be undone.`)) {
      return;
    }
    try {
      const res = await fetch(`/uploads/${fileId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRF-Token': getCsrf() }
      });
      if (!res.ok) {
        const error = await res.text();
        throw new Error(error || 'Delete failed');
      }
      await refreshFiles();
    } catch(err) {
      alert(`Failed to delete file: ${err.message}`);
      console.error(err);
    }
  }

  async function handleBulkDelete() {
    const ids = Array.from(state.selectedIds || []);
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} file(s)? This action cannot be undone.`)) {
      return;
    }
    for (const id of ids) {
      try {
        const res = await fetch(`/uploads/${id}`, {
          method: 'DELETE',
          credentials: 'include',
          headers: { 'X-CSRF-Token': getCsrf() }
        });
        if (!res.ok) {
          const error = await res.text();
          throw new Error(error || 'Delete failed');
        }
      } catch(err) {
        alert(`Failed to delete file ${id}: ${err.message}`);
        console.error(err);
        break;
      }
    }
    state.selectedIds.clear();
    state.selectionMode = false;
    await refreshFiles();
    updateBulkUI();
  }
});
</script>
    """
    return page_shell(body.replace("__VER__", STATIC_VER), "Documents", user_email)


@router.get("/documents/data")
async def documents_data(request: Request):
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with engine.begin() as conn:
        user_row = await conn.exec_driver_sql(
            "SELECT id FROM users WHERE lower(email)=lower(:e) LIMIT 1", {"e": email}
        )
        row = user_row.first()
        if not row:
            raise HTTPException(status_code=401, detail="Not authenticated")
        uid = row[0]

        files_res = await conn.exec_driver_sql(
            """
            SELECT u.id, u.filename, u.mime, u.size, u.storage_key, u.created_at, u.opportunity_id,
                   o.title AS opportunity_title,
                   COALESCE(o.status, '') AS opportunity_status
            FROM user_uploads u
            LEFT JOIN opportunities o ON o.id = u.opportunity_id
            WHERE u.user_id = :uid
            ORDER BY u.created_at DESC
            """,
            {"uid": uid},
        )
        files = []
        for r in files_res.fetchall():
            m = r._mapping
            created = m.get("created_at")
            try:
                dt = created if isinstance(created, datetime) else datetime.fromisoformat(str(created))
                mod_label = dt.strftime("%b %d")
            except Exception:
                mod_label = "Modified"

            size_val = m.get("size") or 0
            def fmt_size(b: int) -> str:
                b = int(b or 0)
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if b < 1024 or unit == "TB":
                        return f"{b:.1f} {unit}" if unit != "B" else f"{b} B"
                    b /= 1024
                return f"{b} B"

            storage_key = m.get("storage_key")
            # Folder bucketing: archive if status contains 'archive', otherwise active
            status = (m.get("opportunity_status") or "").lower()
            folder = "archive" if "archive" in status else "active"

            files.append(
                {
                    "id": m.get("id"),
                    "filename": m.get("filename"),
                    "mime": m.get("mime"),
                    "size": m.get("size"),
                    "size_label": fmt_size(size_val),
                    "download_url": create_presigned_get(storage_key) if storage_key else None,
                    "opportunity_id": m.get("opportunity_id"),
                    "opportunity_title": m.get("opportunity_title") or "Folder",
                    "folder": folder,
                    "modified_label": mod_label,
                }
            )

        opps_res = await conn.exec_driver_sql(
            """
            SELECT o.id, o.title, COALESCE(o.status,'') AS status, COUNT(u.id) AS count
            FROM opportunities o
            LEFT JOIN user_bid_trackers t ON t.opportunity_id = o.id
            LEFT JOIN users u2 ON u2.id = t.user_id
            LEFT JOIN user_uploads u ON u.opportunity_id = o.id AND u.user_id = :uid
            WHERE u2.email = :email OR u.user_id = :uid
            GROUP BY o.id, o.title, o.status
            ORDER BY o.title
            """,
            {"uid": uid, "email": email},
        )
        opps = []
        active_count = 0
        archive_count = 0
        for row in opps_res.fetchall():
            m = row._mapping
            if m.get("id") is None:
                continue
            status = (m.get("status") or "").lower()
            is_archive = "archive" in status
            if is_archive:
                archive_count += m.get("count") or 0
            else:
                active_count += m.get("count") or 0
            opps.append({"id": m["id"], "title": m["title"], "count": m["count"], "status": status})

    folders = [
        {"id": "active", "title": "Active Bids", "count": active_count},
        {"id": "archive", "title": "Archive", "count": archive_count},
    ]

    return {"files": files, "opportunities": opps, "folders": folders}






