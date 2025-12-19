
    document.addEventListener('DOMContentLoaded', function() {
      const scrollProgress = document.getElementById('scrollProgress');
      const content = document.querySelector('.content');
      
      if (content && scrollProgress) {
        content.addEventListener('scroll', () => {
          const scrollTop = content.scrollTop;
          const scrollHeight = content.scrollHeight - content.clientHeight;
          const progress = (scrollTop / scrollHeight) * 100;
          scrollProgress.style.width = progress + '%';
        });
      }

      const tabs = document.querySelectorAll('.account-tab');
      const tabContents = document.querySelectorAll('.tab-content');
      const goToTeamTab = () => {
        const tab = document.querySelector('.account-tab[data-tab="team"]');
        if (!tab) return;
        tab.click();
      };

      function showTab(tabId, options = {}) {
        if (!tabId) return;
        const updateHash = options.updateHash === true;
        tabs.forEach(t => t.classList.remove('active'));
        const activeTab = document.querySelector(`.account-tab[data-tab="${tabId}"]`);
        if (activeTab) activeTab.classList.add('active');

        tabContents.forEach(content => {
          content.classList.remove('active');
          if (content.id === `tab-${tabId}`) {
            content.classList.add('active');
            content.querySelectorAll('.fade-in').forEach((el, i) => {
              el.style.opacity = '0';
              el.style.transform = 'translateY(16px)';
              setTimeout(() => {
                el.style.opacity = '1';
                el.style.transform = 'translateY(0)';
              }, 50 * i);
            });
          }
        });

        if (updateHash) {
          history.replaceState(null, '', `#tab-${tabId}`);
        }
        if (tabId === 'notifications') {
          loadAlertPreferences();
        }
      }

      tabs.forEach(tab => {
        tab.addEventListener('click', () => {
          const tabId = tab.dataset.tab;
          showTab(tabId, { updateHash: true });
        });
      });

      function handleHashNavigation() {
        const hash = window.location.hash || '';
        if (!hash.startsWith('#tab-')) return;
        const tabId = hash.replace('#tab-', '');
        if (!document.querySelector(`.account-tab[data-tab="${tabId}"]`)) return;
        showTab(tabId);
      }
      window.addEventListener('hashchange', handleHashNavigation);

      setTimeout(() => {
        document.querySelectorAll('.fade-in').forEach((el, i) => {
          setTimeout(() => {
            el.style.opacity = '1';
            el.style.transform = 'translateY(0)';
          }, 50 * i);
        });
      }, 100);

      document.querySelectorAll('.toggle input').forEach(toggle => {
        toggle.addEventListener('change', function() {
          const label = this.closest('.notification-item').querySelector('h4').textContent;
          console.log(`${label}: ${this.checked ? 'enabled' : 'disabled'}`);
        });
      });

      document.querySelectorAll('.password-toggle').forEach(btn => {
        btn.addEventListener('click', function() {
          const input = this.previousElementSibling;
          const type = input.type === 'password' ? 'text' : 'password';
          input.type = type;
          this.classList.toggle('active');
        });
      });

      const newPasswordInput = document.querySelector('input[placeholder="Enter new password"]');
      if (newPasswordInput) {
        newPasswordInput.addEventListener('input', function() {
          const password = this.value;
          const strengthFill = document.querySelector('.strength-fill');
          const strengthLabel = document.querySelector('.strength-label');
          
          let strength = 0;
          if (password.length >= 8) strength += 25;
          if (/[A-Z]/.test(password)) strength += 25;
          if (/[0-9]/.test(password)) strength += 25;
          if (/[^A-Za-z0-9]/.test(password)) strength += 25;
          
          strengthFill.style.width = strength + '%';
          
          if (strength === 0) {
            strengthLabel.textContent = 'Enter a password';
            strengthFill.style.background = '#94a3b8';
          } else if (strength <= 25) {
            strengthLabel.textContent = 'Weak';
            strengthFill.style.background = '#ef4444';
          } else if (strength <= 50) {
            strengthLabel.textContent = 'Fair';
            strengthFill.style.background = '#f59e0b';
          } else if (strength <= 75) {
            strengthLabel.textContent = 'Good';
            strengthFill.style.background = '#22c55e';
          } else {
            strengthLabel.textContent = 'Strong';
            strengthFill.style.background = 'var(--primary-gradient)';
          }
        });
      }

      document.getElementById('signOutBtn')?.addEventListener('click', function() {
        if (confirm('Are you sure you want to sign out?')) {
          window.location.href = '/logout';
        }
      });

      // Invite/Team shortcuts
      document.getElementById('qaInviteMember')?.addEventListener('click', goToTeamTab);
      document.getElementById('teamInviteBtn')?.addEventListener('click', goToTeamTab);
      document.getElementById('teamInviteCardBtn')?.addEventListener('click', goToTeamTab);

      // Dynamic wiring -------------------------------------------------
      const planPricing = {
        free: { amount: '$0', period: '/month', limit: 1 },
        starter: { amount: '$29', period: '/month', limit: 3 },
        professional: { amount: '$99', period: '/month', limit: 5 },
        enterprise: { amount: '$299', period: '/month', limit: 50 },
      };
      const fileFields = [
        'ohio_certificate',
        'cert_upload',
        'capability_statement',
        'product_catalogs',
        'ref1_letter',
        'ref2_letter',
        'ref3_letter',
        'ref4_letter',
        'ref5_letter',
        'sub1_certificate',
        'sub2_certificate',
        'sub3_certificate',
        'sub4_certificate',
        'sub5_certificate',
        'insurance_certificate',
        'bonding_letter',
        'price_list_upload',
        'w9_upload',
        'business_license',
        'safety_sheets',
        'warranty_info',
        'previous_contracts',
        'org_chart',
        'digital_signature',
        'signature_image',
        // NEW FIELDS:
        'financial_statements',
        'debarment_certification',
        'labor_compliance_cert',
        'conflict_of_interest',
        'references_combined',
      ];
      const panelSaveStoreKey = 'company_profile_panel_saves';
      const personalDraftKey = 'account_personal_info_draft';
      let personalSnapshot = {};

      function getCSRF() {
        try { return (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || ''; } catch (_) { return ''; }
      }

      let alertPrefsLoaded = false;
      let alertPrefsLoading = false;

      function setAlertPrefsStatus(message, tone = '') {
        const status = document.getElementById('alertPrefsStatus');
        if (!status) return;
        status.textContent = message || '';
        if (tone === 'success') {
          status.style.color = '#16a34a';
        } else if (tone === 'error') {
          status.style.color = '#ef4444';
        } else {
          status.style.color = '';
        }
      }

      function getAlertAgencySelections() {
        return Array.from(document.querySelectorAll('#alertAgencyFilters input[type="checkbox"]'))
          .filter((el) => el.checked)
          .map((el) => el.value);
      }

      function applyAlertPreferences(data = {}) {
        const freqEl = document.getElementById('alertDigestFrequency');
        const smsPhoneEl = document.getElementById('alertSmsPhone');
        const smsOptInEl = document.getElementById('alertSmsOptIn');
        if (freqEl) {
          const freq = String(data.digest_frequency || 'daily').toLowerCase();
          freqEl.value = ['daily', 'weekly', 'none'].includes(freq) ? freq : 'daily';
        }
        if (smsPhoneEl) smsPhoneEl.value = data.sms_phone || '';
        if (smsOptInEl) smsOptInEl.checked = Boolean(data.sms_opt_in);
        const selected = new Set(Array.isArray(data.agency_filter) ? data.agency_filter : []);
        document.querySelectorAll('#alertAgencyFilters input[type="checkbox"]').forEach((el) => {
          el.checked = selected.has(el.value);
        });
      }

      async function loadAlertPreferences(force = false) {
        if (alertPrefsLoading) return;
        if (alertPrefsLoaded && !force) return;
        const freqEl = document.getElementById('alertDigestFrequency');
        if (!freqEl) return;
        alertPrefsLoading = true;
        setAlertPrefsStatus('Loading preferences...');
        try {
          const res = await fetch('/api/me/preferences', { credentials: 'include' });
          if (!res.ok) throw new Error('load failed');
          const data = await res.json();
          applyAlertPreferences(data);
          alertPrefsLoaded = true;
          setAlertPrefsStatus('');
        } catch (_) {
          setAlertPrefsStatus('Could not load preferences.', 'error');
        } finally {
          alertPrefsLoading = false;
        }
      }

      async function saveAlertPreferences() {
        const btn = document.getElementById('saveAlertPrefs');
        const freqEl = document.getElementById('alertDigestFrequency');
        const smsPhoneEl = document.getElementById('alertSmsPhone');
        const smsOptInEl = document.getElementById('alertSmsOptIn');
        if (!freqEl) return;
        btn && (btn.disabled = true);
        setAlertPrefsStatus('');
        try {
          const payload = {
            digest_frequency: freqEl.value,
            agency_filter: getAlertAgencySelections(),
            sms_phone: (smsPhoneEl?.value || '').trim(),
            sms_opt_in: Boolean(smsOptInEl?.checked),
          };
          const res = await fetch('/api/me/preferences', {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCSRF(),
            },
            body: JSON.stringify(payload),
          });
          if (!res.ok) throw new Error('save failed');
          alertPrefsLoaded = true;
          setAlertPrefsStatus('Saved successfully!', 'success');
        } catch (_) {
          setAlertPrefsStatus('Could not save preferences.', 'error');
        } finally {
          btn && (btn.disabled = false);
        }
      }

      function initials(str) {
        if (!str) return '??';
        const parts = str.trim().split(/\s+/);
        if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
        if (str.includes('@')) return str.split('@')[0].slice(0, 2).toUpperCase();
        return str.slice(0, 2).toUpperCase();
      }

      function formatMonthYear(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        return d.toLocaleString('en-US', { month: 'short', year: 'numeric' });
      }

      function personalFormValues() {
        return {
          first_name: (document.getElementById('profileFirstName')?.value || '').trim(),
          last_name: (document.getElementById('profileLastName')?.value || '').trim(),
          email: (document.getElementById('profileEmail')?.value || '').trim(),
          phone: (document.getElementById('profilePhone')?.value || '').trim(),
          title: (document.getElementById('profileJobTitle')?.value || '').trim(),
        };
      }

      function applyPersonalValues(values = {}) {
        const { first_name, last_name, email, phone, title } = values;
        const pf = document.getElementById('profileFirstName');
        const pl = document.getElementById('profileLastName');
        const pe = document.getElementById('profileEmail');
        const pp = document.getElementById('profilePhone');
        const pj = document.getElementById('profileJobTitle');
        if (pf && first_name !== undefined && first_name !== null) pf.value = first_name;
        if (pl && last_name !== undefined && last_name !== null) pl.value = last_name;
        if (pe && email !== undefined && email !== null) pe.value = email;
        if (pp && phone !== undefined && phone !== null) pp.value = phone;
        if (pj && title !== undefined && title !== null) pj.value = title;
      }

      function loadPersonalDraft(preferWhenMissing = false) {
        try {
          const raw = localStorage.getItem(personalDraftKey);
          if (!raw) return;
          const draft = JSON.parse(raw);
          if (preferWhenMissing) {
            const current = personalFormValues();
            applyPersonalValues({
              first_name: current.first_name || draft.first_name,
              last_name: current.last_name || draft.last_name,
              email: current.email || draft.email,
              phone: current.phone || draft.phone,
              title: current.title || draft.title,
            });
          } else {
            applyPersonalValues(draft);
          }
        } catch (_) { /* ignore */ }
      }

      function savePersonalDraft(values) {
        try {
          localStorage.setItem(personalDraftKey, JSON.stringify(values));
        } catch (_) { /* ignore */ }
      }

      function ensureFileContainer(field) {
        const input = document.querySelector(`input[name="${field}"]`);
        if (!input) return null;
        const uploadArea = input.closest('.file-upload-area') || input.closest('.file-upload-area.small') || input.parentElement;
        if (!uploadArea) return null;
        const existingWrap = uploadArea.closest('.file-upload-container');
        if (existingWrap) return existingWrap.querySelector('[data-file-existing]');
        const group = uploadArea.closest('.form-group') || uploadArea.parentElement;
        if (!group) return null;
        const container = document.createElement('div');
        container.className = 'file-upload-container';
        const existingDiv = createExistingTemplate(field);
        uploadArea.dataset.fileUpload = field;
        container.appendChild(existingDiv);
        container.appendChild(uploadArea);
        const legacyLink = group.querySelector(`[data-file-link="${field}"]`);
        if (legacyLink) legacyLink.remove();
        const status = group.querySelector(`[data-file-status="${field}"]`);
        if (status) status.remove();
        group.appendChild(container);
        return existingDiv;
      }

      function isImageUrl(url) {
        if (!url) return false;
        const urlWithoutQuery = String(url).split('?')[0];
        return (
          /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(urlWithoutQuery) ||
          /[?&](content-type|type)=image/i.test(String(url))
        );
      }

      function extractFilename(str) {
        if (!str) return '';
        const legacyMatch = String(str).match(/filename=['"]?([^'")]+)['"]?/i);
        if (legacyMatch && legacyMatch[1]) return legacyMatch[1];
        const parts = String(str).split(/[\\/]/);
        return parts.pop() || '';
      }

      function showExistingFile(field, name, url) {
        // Ensure container exists
        let existingDiv = document.querySelector(`[data-file-existing="${field}"]`);
        let uploadDiv = document.querySelector(`[data-file-upload="${field}"]`);
        
        // If elements don't exist, create them
        if (!existingDiv || !uploadDiv) {
          const created = ensureFileContainer(field);
          if (!created) return; // No input found for this field
          existingDiv = document.querySelector(`[data-file-existing="${field}"]`);
          uploadDiv = document.querySelector(`[data-file-upload="${field}"]`);
        }
        
        if (!existingDiv || !uploadDiv) return;

        const nameEl = document.querySelector(`[data-file-name="${field}"]`);
        const downloadLink = document.querySelector(`[data-file-download="${field}"]`);
        const previewEl = document.querySelector(`[data-file-preview="${field}"]`);

        // Determine display name
        let displayName = (name || '').trim();
        if (!displayName) displayName = extractFilename(url) || extractFilename(name);
        if (!displayName && url) displayName = 'Uploaded file';
        
        const hasSomething = Boolean(displayName || url);

        if (hasSomething) {
          // Show existing file, hide upload area
          existingDiv.style.display = 'flex';
          uploadDiv.style.display = 'none';
          
          // Update filename
          if (nameEl) nameEl.textContent = displayName || 'Uploaded file';
          
          // Update download link
          if (downloadLink) {
            if (url) {
              downloadLink.href = url;
              downloadLink.style.display = 'flex';
            } else {
              downloadLink.style.display = 'none';
            }
          }
          
          // Update preview
          if (previewEl) {
            if (url && isImageUrl(url)) {
              const img = document.createElement('img');
              img.src = url;
              img.alt = displayName || 'Preview';
              img.loading = 'lazy';
              img.onerror = function() {
                const ext = (displayName.split('.').pop() || '').toUpperCase();
                previewEl.innerHTML = `<div class="file-preview-icon">${ext || 'FILE'}</div>`;
                previewEl.style.display = 'flex';
              };
              previewEl.innerHTML = '';
              previewEl.appendChild(img);
              previewEl.style.display = 'flex';
            } else {
              // Show file type icon
              const ext = (displayName.split('.').pop() || '').toUpperCase();
              previewEl.innerHTML = `<div class="file-preview-icon">${ext || 'FILE'}</div>`;
              previewEl.style.display = 'flex';
            }
          }
        } else {
          // No file - show upload area, hide existing
          existingDiv.style.display = 'none';
          uploadDiv.style.display = 'block';
          if (previewEl) {
            previewEl.innerHTML = '';
            previewEl.style.display = 'none';
          }
        }
        
        // Rebind replace button for this field
        bindFileReplaceButtons();
      }

      function markFileSelection(input, displayName) {
        if (!input) return;
        const field = input.getAttribute('name');
        const uploadDiv = input.closest('[data-file-upload]');
        const existingDiv = document.querySelector(`[data-file-existing="${field}"]`);
        const label = input.closest('.file-upload-area')?.querySelector('.file-upload-label');
        const text = label?.querySelector('.upload-text');
        const hint = label?.querySelector('.upload-hint');
        
        if (displayName && text) {
          text.textContent = `Uploaded: ${displayName}`;
          text.style.color = '#126a45';
          text.style.fontWeight = '600';
        }
        if (hint) {
          hint.textContent = 'Ready to save';
          hint.style.color = '#126a45';
        }
        if (existingDiv && uploadDiv) {
          existingDiv.style.display = 'none';
          uploadDiv.style.display = 'block';
        }
      }

      function createExistingTemplate(field) {
        const existingDiv = document.createElement('div');
        existingDiv.className = 'file-existing';
        existingDiv.dataset.fileExisting = field;
        existingDiv.style.display = 'none';
        existingDiv.innerHTML = `
          <div class="file-existing-preview" data-file-preview="${field}" style="display:none;"></div>
          <div class="file-existing-info">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <div class="file-existing-details">
              <span class="file-existing-name" data-file-name="${field}">—</span>
              <span class="file-existing-meta">Uploaded previously</span>
            </div>
          </div>
          <div class="file-existing-actions">
            <a class="file-existing-download" data-file-download="${field}" href="#" target="_blank" rel="noopener" title="Download" style="display:none;">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </a>
            <button type="button" class="file-existing-replace" data-file-replace="${field}" title="Replace">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="1 4 1 10 7 10"></polyline>
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
              </svg>
            </button>
          </div>
        `;
        return existingDiv;
      }

      function upgradeFileInputs() {
        document.querySelectorAll('input[type="file"][name]').forEach((input) => {
          const field = input.getAttribute('name');
          if (!field) return;
          const uploadArea = input.closest('.file-upload-area') || input.closest('.file-upload-area.small') || input.parentElement;
          if (!uploadArea) return;
          
          // Already upgraded? ensure data attribute exists and skip
          if (uploadArea.closest('.file-upload-container')) {
            if (!uploadArea.dataset.fileUpload) {
              uploadArea.dataset.fileUpload = field;
            }
            return;
          }
          
          uploadArea.dataset.fileUpload = field;
          const group = uploadArea.closest('.form-group') || uploadArea.parentElement;
          if (!group) return;
          
          // Create container and structure
          const container = document.createElement('div');
          container.className = 'file-upload-container';
          const existingDiv = createExistingTemplate(field);
          
          // Insert before uploadArea to preserve position, then move uploadArea inside
          uploadArea.parentNode.insertBefore(container, uploadArea);
          container.appendChild(existingDiv);
          container.appendChild(uploadArea);
          
          // Clean up legacy elements
          const legacyLink = group.querySelector(`[data-file-link="${field}"]`);
          if (legacyLink) legacyLink.remove();
          const status = group.querySelector(`[data-file-status="${field}"]`);
          if (status) status.remove();
        });
      }

      function bindFileReplaceButtons() {
        document.querySelectorAll('[data-file-replace]').forEach((btn) => {
          if (btn.dataset.boundReplace === '1') return;
          btn.dataset.boundReplace = '1';
          btn.addEventListener('click', () => {
            const field = btn.dataset.fileReplace;
            const existingDiv = document.querySelector(`[data-file-existing="${field}"]`);
            const uploadDiv = document.querySelector(`[data-file-upload="${field}"]`);
            const input = document.querySelector(`input[name="${field}"]`);
            if (existingDiv) existingDiv.style.display = 'none';
            if (uploadDiv) uploadDiv.style.display = 'block';
            if (input) input.click();
          });
        });
      }

      function loadPanelSaveTimes() {
        try {
          const raw = localStorage.getItem(panelSaveStoreKey);
          return raw ? JSON.parse(raw) : {};
        } catch (_) {
          return {};
        }
      }

      function savePanelSaveTimes(map) {
        try {
          localStorage.setItem(panelSaveStoreKey, JSON.stringify(map));
        } catch (_) { /* ignore */ }
      }

      function formatSaveTime(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        
        // Use consistent, readable format instead of toLocaleString()
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays}d ago`;
        
        // For older dates, use readable format
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
      }

      function updatePanelSaveMeta(panelKey, ts) {
        document.querySelectorAll(`[data-panel-save="${panelKey}"]`).forEach((el) => {
          el.textContent = ts ? `Last saved ${formatSaveTime(ts)}` : '';
        });
      }

      function recordPanelSave(panelKey) {
        if (!panelKey) return;
        const map = loadPanelSaveTimes();
        const now = new Date().toISOString();
        map[panelKey] = now;
        savePanelSaveTimes(map);
        updatePanelSaveMeta(panelKey, now);
      }

      function recordAllPanelSaves() {
        const map = loadPanelSaveTimes();
        const now = new Date().toISOString();
        document.querySelectorAll('[data-panel-save]').forEach((el) => {
          const key = el.getAttribute('data-panel-save');
          if (key) {
            map[key] = now;
            updatePanelSaveMeta(key, now);
          }
        });
        savePanelSaveTimes(map);
      }

      function panelStatus(panel) {
        const inputs = Array.from(panel.querySelectorAll('input, textarea, select')).filter((el) => {
          if (!el.closest('.panel-content')) return false;
          if (el.type === 'hidden') return false;
          return true;
        });
        const total = inputs.length;
        if (!total) return 'red';
        let filled = 0;
        inputs.forEach((el) => {
          if (el.type === 'file') {
            const field = el.name;
            const existingEl = panel.querySelector(`[data-file-existing="${field}"]`);
            const hasExisting = existingEl && existingEl.style.display !== 'none';
            const hasFile = (el.files && el.files.length) || hasExisting;
            if (hasFile) filled += 1;
            return;
          }
          if (el.type === 'checkbox' || el.type === 'radio') {
            if (el.checked) filled += 1;
            return;
          }
          if ((el.value || '').trim()) filled += 1;
        });
        if (filled === 0) return 'red';
        if (filled === total) return 'green';
        return 'yellow';
      }

      function updatePanelStatuses() {
        document.querySelectorAll('.company-profile-section .profile-panel').forEach((panel) => {
          const status = panelStatus(panel);
          panel.classList.remove('panel-status-green', 'panel-status-yellow', 'panel-status-red');
          panel.classList.add(`panel-status-${status}`);
        });
      }

      function setUsage(textEl, fillEl, used, limit, gradient) {
        if (!textEl || !fillEl) return;
        const unlimited = !limit || limit === Infinity;
        textEl.textContent = unlimited ? `${used} / Unlimited` : `${used} / ${limit}`;
        const pct = unlimited ? 100 : Math.min(100, Math.round((used / limit) * 100));
        fillEl.style.width = `${pct}%`;
        if (gradient) fillEl.style.background = gradient;
      }

      async function savePersonalInfo() {
        const status = document.getElementById('personalInfoStatus');
        const btn = document.getElementById('savePersonalInfo');
        const values = personalFormValues();
        if (status) status.textContent = '';
        if (!values.first_name || !values.last_name) {
          if (status) status.textContent = 'First and last name are required.';
          return;
        }
        btn && (btn.disabled = true);
        try {
          const res = await fetch('/api/account/profile', {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCSRF(),
            },
            body: JSON.stringify({
              first_name: values.first_name,
              last_name: values.last_name,
            }),
          });
          if (!res.ok) throw new Error('save failed');
          personalSnapshot = { ...values };
          savePersonalDraft(values);
          if (status) status.textContent = 'Saved.';
        } catch (_) {
          if (status) status.textContent = 'Could not save right now.';
        } finally {
          btn && (btn.disabled = false);
        }
      }

      function resetPersonalInfo() {
        applyPersonalValues(personalSnapshot);
        const status = document.getElementById('personalInfoStatus');
        if (status) status.textContent = '';
      }

      function renderTeam(members, seatLimit) {
        const grid = document.getElementById('teamGrid');
        if (!grid) return;
        const palette = [
          'linear-gradient(135deg, #126a45, #22c55e)',
          'linear-gradient(135deg, #3b82f6, #60a5fa)',
          'linear-gradient(135deg, #8b5cf6, #a78bfa)',
          'linear-gradient(135deg, #f59e0b, #fbbf24)',
        ];
        const cards = members.map((m, idx) => {
          const role = (m.role || 'member').toLowerCase();
          const badgeClass = role === 'owner' ? 'owner' : role === 'admin' ? 'admin' : 'member';
          const bg = palette[idx % palette.length];
          const status = m.accepted ? 'online' : 'offline';
          const statusText = m.accepted ? 'Online now' : 'Pending invite';
          const joined = m.accepted_at ? `Joined ${new Date(m.accepted_at).toLocaleDateString()}` : `Invited ${new Date(m.invited_at || Date.now()).toLocaleDateString()}`;
          const removeBtn = role !== 'owner'
            ? `<button class="team-card-menu" data-remove="${m.id}" data-email="${m.email || ''}">...</button>`
            : '';
          const avatar = m.avatar_url
            ? `<div class="team-card-avatar has-image"><img src="${m.avatar_url}" alt="${m.name || m.email}"></div>`
            : `<div class="team-card-avatar" style="background:${bg};">${initials(m.name || m.email)}</div>`;
          return `
            <div class="team-card ${role === 'owner' ? 'owner-card' : ''}">
              <div class="team-card-header">
                ${avatar}
                <div class="team-card-badge ${badgeClass}">${role.charAt(0).toUpperCase() + role.slice(1)}</div>
              </div>
              <div class="team-card-body">
                <h4>${m.name || m.email}</h4>
                <p>${m.email || ''}</p>
                <span class="team-card-status ${status}">
                  <span class="status-dot"></span>
                  ${statusText}
                </span>
              </div>
              <div class="team-card-footer">
                <span class="team-card-joined">${joined}</span>
                ${removeBtn}
              </div>
            </div>
          `;
        });
        const remaining = Math.max(0, (seatLimit || members.length) - members.length);
        cards.push(`
          <div class="team-card add-card" id="teamAddCard">
            <div class="add-card-content">
              <div class="add-card-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19"></line>
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
              </div>
              <h4>Add Team Member</h4>
              <p>${remaining} seats remaining</p>
            </div>
          </div>
        `);
        grid.innerHTML = cards.join('');
      }

      function renderTeamPreview(members){
        const wrap = document.getElementById('teamListCard');
        if (!wrap) return;
        if (!members || !members.length) {
          wrap.innerHTML = "<div class='muted'>No teammates yet.</div>";
          return;
        }
        const palette = [
          'linear-gradient(135deg, #126a45, #22c55e)',
          'linear-gradient(135deg, #3b82f6, #60a5fa)',
          'linear-gradient(135deg, #8b5cf6, #a78bfa)',
          'linear-gradient(135deg, #f59e0b, #fbbf24)',
        ];
        wrap.innerHTML = members.map((m, idx) => {
          const role = (m.role || 'member').toLowerCase();
          const bg = palette[idx % palette.length];
          const avatar = m.avatar_url
            ? `<div class="member-avatar has-image"><img src="${m.avatar_url}" alt="${m.name || m.email}"></div>`
            : `<div class="member-avatar" style="background:${bg};">${initials(m.name || m.email)}</div>`;
          return `
            <div class="team-member">
              ${avatar}
              <div class="member-info">
                <span class="member-name">${m.name || m.email}</span>
                <span class="member-role">${role.charAt(0).toUpperCase() + role.slice(1)}</span>
              </div>
            </div>
          `;
        }).join('');
      }

      function formatActivityTime(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        return d.toLocaleString('en-US', { month: 'short', day: 'numeric' });
      }

      function renderActivity(entries) {
        const list = document.getElementById('activityList');
        if (!list) return;
        if (!entries || !entries.length) {
          list.innerHTML = "<div class='muted'>No recent activity yet.</div>";
          return;
        }
        const iconFor = (type) => {
          if (type === 'upload') return 'blue';
          return 'green';
        };
        list.innerHTML = entries.slice(0, 5).map((a) => {
          const color = iconFor(a.type);
          const who = a.who || '';
          const verb = a.verb || '';
          const obj = a.obj || '';
          const when = formatActivityTime(a.when);
          return `
            <div class="activity-item">
              <div class="activity-icon ${color}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </div>
              <div class="activity-content">
                <span class="activity-text">${who ? `<strong>${who}</strong> ` : ''}${verb} ${obj ? `<strong>${obj}</strong>` : ''}</span>
                <span class="activity-time">${when}</span>
              </div>
            </div>
          `;
        }).join('');
      }

      function renderPendingInvites(members) {
        const wrap = document.getElementById('pendingInvites');
        if (!wrap) return;
        const pending = (members || []).filter(m => !m.accepted);
        if (!pending.length) {
          wrap.innerHTML = "<div class='muted'>No pending invites.</div>";
          return;
        }
        wrap.innerHTML = pending
          .map((m) => {
            const sentLabel = m.invited_at
              ? `Sent ${new Date(m.invited_at).toLocaleDateString()}`
              : 'Sent';
            return `
              <div class="pending-invite" data-invite-id="${m.id}" data-email="${m.email || m.invited_email || ''}">
                <div class="pending-avatar">${initials(m.name || m.email || m.invited_email)}</div>
                <div class="pending-info">
                  <span class="pending-email">${m.email || m.invited_email || ''}</span>
                  <span class="pending-sent">${sentLabel}</span>
                </div>
                <div class="pending-actions">
                  <button class="btn-ghost" data-resend="${m.email || m.invited_email || ''}">Resend</button>
                  <button class="btn-danger-ghost" data-revoke="${m.id}">Revoke</button>
                </div>
              </div>
            `;
          })
          .join('');
      }

      function bindTeamHandlers() {
        const grid = document.getElementById('teamGrid');
        if (!grid) return;
        grid.addEventListener('click', async (e) => {
          if (e.target.closest('#teamAddCard')) {
            inviteFlow();
            return;
          }
          const removeBtn = e.target.closest('[data-remove]');
          if (removeBtn) {
            const id = removeBtn.getAttribute('data-remove');
            const email = removeBtn.getAttribute('data-email') || 'this member';
            if (!id) return;
            if (!confirm(`Remove ${email} from your team?`)) return;
            removeBtn.disabled = true;
            try {
              const res = await fetch(`/api/team/members/${id}/remove`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'X-CSRF-Token': getCSRF() },
              });
              if (!res.ok) throw new Error('Failed');
              await loadAccount();
            } catch (_) {
              alert('Could not remove member (owner required).');
            } finally {
              removeBtn.disabled = false;
            }
          }
        });

        const pendingWrap = document.getElementById('pendingInvites');
        if (pendingWrap) {
          pendingWrap.addEventListener('click', async (e) => {
            const resend = e.target.closest('[data-resend]');
            if (resend) {
              const email = resend.getAttribute('data-resend');
              if (!email) return;
              resend.disabled = true;
              try {
                const res = await fetch('/api/team/invite', {
                  method: 'POST',
                  credentials: 'include',
                  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCSRF() },
                  body: JSON.stringify({ email }),
                });
                if (!res.ok) throw new Error('failed');
                alert('Invitation resent.');
                await loadAccount();
              } catch (_) {
                alert('Could not resend invite.');
              } finally {
                resend.disabled = false;
              }
              return;
            }
            const revoke = e.target.closest('[data-revoke]');
            if (revoke) {
              const id = revoke.getAttribute('data-revoke');
              const email = revoke.closest('.pending-invite')?.getAttribute('data-email') || 'this invite';
              if (!id) return;
              if (!confirm(`Revoke invite for ${email}?`)) return;
              revoke.disabled = true;
              try {
                const res = await fetch(`/api/team/members/${id}/remove`, {
                  method: 'POST',
                  credentials: 'include',
                  headers: { 'X-CSRF-Token': getCSRF() },
                });
                if (!res.ok) throw new Error('failed');
                await loadAccount();
              } catch (_) {
                alert('Could not revoke invite (owner required).');
              } finally {
                revoke.disabled = false;
              }
            }
          });
        }
      }

      const inviteFlow = () => {
        // Skip the email prompt; send users to the Team tab to manage invites.
        document.querySelector('.account-tab[data-tab=\"team\"]')?.click();
      };

      async function loadAccount() {
        const res = await fetch('/api/account/overview', { credentials: 'include' });
        if (!res.ok) {
          console.error('Failed to load account overview', res.status);
          return;
        }
        const data = await res.json();
        const user = data.user || {};
        const plan = data.plan || {};
        const usage = data.usage || {};
        const team = data.team || {};
        const name = user.name || user.email || 'My Account';
        const nameEl = document.getElementById('accountName');
        if (nameEl) nameEl.textContent = name;
        const emailEl = document.getElementById('accountEmail');
        if (emailEl) emailEl.textContent = user.email || '';
        const pf = document.getElementById('profileFirstName');
        if (pf) pf.value = user.first_name || '';
        const pl = document.getElementById('profileLastName');
        if (pl) pl.value = user.last_name || '';
        const pe = document.getElementById('profileEmail');
        if (pe) pe.value = user.email || '';
        personalSnapshot = {
          first_name: user.first_name || '',
          last_name: user.last_name || '',
          email: user.email || '',
          phone: document.getElementById('profilePhone')?.value || '',
          title: document.getElementById('profileJobTitle')?.value || '',
        };
        loadPersonalDraft(true);
        const avatar = document.getElementById('avatarInitials');
        if (avatar && avatar.querySelector('span')) avatar.querySelector('span').textContent = initials(name);
        const topAvatar = document.getElementById('topAvatar');
        if (topAvatar) topAvatar.textContent = initials(name);
        // Load avatar if exists
        if (user.avatar_url) {
          const largeAvatar = document.getElementById('avatarInitials');
          largeAvatar.classList.add('has-image');
          let img = largeAvatar.querySelector('img');
          if (!img) {
            img = document.createElement('img');
            largeAvatar.insertBefore(img, largeAvatar.firstChild);
          }
          img.src = user.avatar_url;
          
          const topAvatar = document.getElementById('topAvatar');
          if (topAvatar) {
            topAvatar.innerHTML = `<img src="${user.avatar_url}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
          }
        }
        const badge = document.getElementById('planBadge');
        const badgeLabel = document.getElementById('planBadgeLabel');
        if (badge) badge.style.display = plan.label ? 'inline-flex' : 'none';
        if (badgeLabel) badgeLabel.textContent = plan.label || '';
        if (badge && !badgeLabel) badge.textContent = plan.label || '';
        const teamBadge = document.getElementById('teamBadge');
        const teamBadgeLabel = document.getElementById('teamBadgeLabel');
        if (teamBadge) {
          const isTeam = !!(data.team && data.team.team_id);
          const roleLabel = (user.role || '').toLowerCase();
          if (isTeam) {
            teamBadge.style.display = 'inline-flex';
            if (teamBadgeLabel) teamBadgeLabel.textContent = roleLabel === 'owner' ? 'Team Owner' : 'Team Member';
          } else {
            teamBadge.style.display = 'none';
          }
        }
        const verifiedBadge = document.getElementById('verifiedBadge');
        if (verifiedBadge) {
          verifiedBadge.style.display = user.email_verified ? 'inline-flex' : 'none';
        }
        const memberSinceEl = document.getElementById('memberSince');
        if (memberSinceEl) {
          const niceDate = formatMonthYear(user.created_at);
          memberSinceEl.textContent = niceDate ? `Member since ${niceDate}` : 'Member';
        }
        const usagePeriodEl = document.querySelector('.usage-card .card-period');
        if (usagePeriodEl) {
          const now = new Date();
          const end = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
          const month = now.toLocaleString('en-US', { month: 'short' });
          usagePeriodEl.textContent = `${month} 1 - ${month} ${end}`;
        }
        const planNameEl = document.getElementById('planName');
        if (planNameEl) planNameEl.textContent = plan.label || '';
        const planPriceEl = document.getElementById('planPrice');
        if (planPriceEl) planPriceEl.textContent = plan.amount || '$0';
        const planPeriodEl = document.getElementById('planPeriod');
        if (planPeriodEl) planPeriodEl.textContent = plan.period || '/month';
        const topTierLabel = document.getElementById('topTierLabel');
        if (topTierLabel) topTierLabel.textContent = plan.label || '';
        const planNextBillingEl = document.getElementById('planNextBilling');
        if (planNextBillingEl) {
          const raw = plan.next_billing || plan.next_billing_at || plan.next_invoice_at;
          if (raw) {
            const d = new Date(raw);
            planNextBillingEl.textContent = isNaN(d.getTime()) ? raw : d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });
          } else {
            planNextBillingEl.textContent = '--';
          }
        }
        const tierKey = (user.tier_key || '').toLowerCase();
        const seatLimit = (planPricing[tierKey] || {}).limit || usage.team || 5;
        setUsage(document.getElementById('usageBids'), document.getElementById('usageBidsFill'), usage.tracked || 0, Infinity, 'var(--primary-gradient)');
        setUsage(document.getElementById('usageTeam'), document.getElementById('usageTeamFill'), usage.team || 0, seatLimit);
        const docsMB = (usage.documents?.bytes || 0) / (1024 * 1024);
      setUsage(document.getElementById('usageDocs'), document.getElementById('usageDocsFill'), Math.round(docsMB), 5000);
      setUsage(document.getElementById('usageTokens'), document.getElementById('usageTokensFill'), usage.token_calls || 0, 10000);

        const teamMembers = team.members || [];
        const teamCountEl = document.getElementById('teamCount');
        const teamAvailEl = document.getElementById('teamAvailable');
        if (teamCountEl) teamCountEl.textContent = teamMembers.length.toString();
        if (teamAvailEl) teamAvailEl.textContent = Math.max(0, seatLimit - teamMembers.length).toString();
        renderTeam(teamMembers, seatLimit);
        renderTeamPreview(teamMembers);
        renderPendingInvites(teamMembers);
        renderActivity(data.activity || []);
      }

      function calculateProfileProgress() {
        const requiredFields = [
          'legal_name', 'ein', 'business_type', 'state_incorp', 'year_founded',
          'hq_address', 'city', 'state', 'zip',
          'primary_name', 'primary_email', 'primary_phone',
          'years_experience', 'experience',
          'gl_coverage', 'wc_coverage',
          'signer_name', 'signer_title'
        ];

        const form = document.getElementById('companyProfileForm');
        if (!form) return 0;

        let filled = 0;
        requiredFields.forEach((name) => {
          const el = form.querySelector(`[name="${name}"]`);
          if (el && el.value && el.value.trim()) filled += 1;
        });

        const ref1Business = form.querySelector('[name="ref1_business"]');
        if (ref1Business && ref1Business.value.trim()) filled += 1;

        const total = requiredFields.length + 1;
        const percent = Math.round((filled / total) * 100);

        const valueEl = document.getElementById('profileCompleteness');
        const fillEl = document.getElementById('profileProgressFill');
        const hintEl = document.getElementById('profileProgressHint');

        if (valueEl) valueEl.textContent = `${percent}%`;
        if (fillEl) fillEl.style.width = `${percent}%`;
        if (hintEl) {
          if (percent < 30) hintEl.textContent = 'Add basic company info to get started';
          else if (percent < 60) hintEl.textContent = 'Add contacts and experience details';
          else if (percent < 90) hintEl.textContent = 'Almost there! Add insurance and references';
          else hintEl.textContent = '✓ Great! Your profile covers most RFP requirements';
        }

        return percent;
      }

      function setMainFieldValue(name, value) {
        const field = document.querySelector(`#companyProfileForm [name="${name}"]`);
        if (!field) return;
        if (field.type === 'checkbox') {
          field.checked = value === true || value === 'true' || value === 'on';
        } else {
          field.value = value ?? '';
        }
        field.dispatchEvent(new Event('input', { bubbles: true }));
        field.dispatchEvent(new Event('change', { bubbles: true }));
      }

      function getMainFieldValue(name) {
        const field = document.querySelector(`#companyProfileForm [name="${name}"]`);
        if (!field) return '';
        if (field.type === 'checkbox') return field.checked;
        return field.value || '';
      }

      function initSubAccordions() {
        document.querySelectorAll('.sub-accordion-header').forEach((btn) => {
          btn.addEventListener('click', () => {
            const item = btn.closest('.sub-accordion-item');
            if (!item) return;
            const isOpen = item.classList.contains('open');
            item.classList.toggle('open');
            btn.setAttribute('aria-expanded', (!isOpen).toString());
          });
        });
      }

      function initQuickSetupWizard() {
        const modal = document.getElementById('quickSetupModal');
        const startBtn = document.getElementById('startQuickSetup');
        const skipBtn = document.getElementById('skipQuickSetup');
        const closeBtn = document.getElementById('quickSetupClose');
        const backBtn = document.getElementById('quickBackBtn');
        const nextBtn = document.getElementById('quickNextBtn');
        const steps = Array.from(document.querySelectorAll('.quick-step'));
        const stepLabel = document.getElementById('quickStepLabel');
        const quickCard = document.getElementById('quickSetupCard');
        const dismissedKey = 'quickSetupDismissed';
        let stepIndex = 0;

        if (!steps.length) return;

        const total = steps.length;

        const syncFromMain = (stepEl) => {
          stepEl.querySelectorAll('[data-field]').forEach((input) => {
            const name = input.dataset.field;
            const val = getMainFieldValue(name);
            if (input.type === 'checkbox') {
              input.checked = val === true || val === 'true' || val === 'on';
            } else {
              input.value = val || '';
            }
          });
        };

        const persistStep = (stepEl) => {
          stepEl.querySelectorAll('[data-field]').forEach((input) => {
            const name = input.dataset.field;
            const val = input.type === 'checkbox' ? input.checked : input.value;
            setMainFieldValue(name, val);
          });
          updatePanelStatuses();
          calculateProfileProgress();
          return true;
        };

        const showStep = (idx) => {
          steps.forEach((el, i) => el.classList.toggle('active', i === idx));
          if (stepLabel) stepLabel.textContent = `Step ${idx + 1} of ${total}`;
          if (backBtn) backBtn.style.visibility = idx === 0 ? 'hidden' : 'visible';
          if (nextBtn) nextBtn.textContent = idx === total - 1 ? 'Finish' : 'Next';
          syncFromMain(steps[idx]);
        };

        const openWizard = () => {
          if (!modal) return;
          modal.style.display = 'flex';
          stepIndex = 0;
          showStep(stepIndex);
        };

        const closeWizard = () => {
          if (!modal) return;
          modal.style.display = 'none';
          localStorage.setItem(dismissedKey, '1');
        };

        startBtn?.addEventListener('click', () => {
          openWizard();
        });

        skipBtn?.addEventListener('click', () => {
          localStorage.setItem(dismissedKey, '1');
          if (quickCard) quickCard.style.display = 'none';
        });

        closeBtn?.addEventListener('click', closeWizard);

        nextBtn?.addEventListener('click', () => {
          if (!persistStep(steps[stepIndex])) return;
          if (stepIndex < total - 1) {
            stepIndex += 1;
            showStep(stepIndex);
          } else {
            closeWizard();
          }
        });

        backBtn?.addEventListener('click', () => {
          if (!persistStep(steps[stepIndex])) return;
          if (stepIndex > 0) {
            stepIndex -= 1;
            showStep(stepIndex);
          }
        });

        if (modal) {
          modal.addEventListener('click', (e) => {
            if (e.target === modal) closeWizard();
          });
        }

        if (localStorage.getItem(dismissedKey)) {
          if (quickCard) quickCard.style.display = 'none';
        }
      }

      async function loadCompanyProfile() {
        try {
          const status = document.getElementById('companyProfileStatus');
          if (status) status.textContent = '';
          const res = await fetch('/api/company-profile', { credentials: 'include' });
          if (!res.ok) return;
          const resp = await res.json();
          const payload = resp.data || {};
          const files = resp.files || {};
          // DEBUG: Log what files the API returns
          console.log('[loadCompanyProfile] files from API:', files);
          console.log('[loadCompanyProfile] payload keys:', Object.keys(payload));
          const form = document.getElementById('companyProfileForm');
          if (!form) return;
          Array.from(form.querySelectorAll('[name]')).forEach((el) => {
            const key = el.getAttribute('name');
            if (!key) return;
            if (el.type === 'checkbox') {
              if (el.dataset.multi === 'true') {
                const values = (payload[key] || '').split(',').map((v) => v.trim());
                el.checked = values.includes(el.value);
              } else {
                el.checked = !!payload[key];
              }
            } else if (el.type === 'radio') {
              el.checked = payload[key] === el.value;
            } else if (el.multiple && el.tagName === 'SELECT') {
              const values = (payload[key] || '').split(',').map((v) => v.trim()).filter(Boolean);
              Array.from(el.options).forEach((opt) => { opt.selected = values.includes(opt.value); });
            } else {
              el.value = payload[key] || '';
            }
          });

          // show file links
          Object.entries(files).forEach(([field, meta]) => {
            showExistingFile(field, meta?.name || meta?.key || '', meta?.url);
          });
          // Also reflect stored filenames even if no URL available
          Object.keys(payload || {}).forEach((key) => {
            if (!key.endsWith('_name')) return;
            const field = key.replace(/_name$/, '');
            const existingName = payload[key];
            if (existingName) {
              const meta = files[field] || {};
              showExistingFile(field, existingName, meta.url);
            }
          });
          // Fallback: if we have a stored key but no name, still show something
          Object.keys(payload || {}).forEach((key) => {
            if (key.endsWith('_name')) return;
            if (!fileFields.includes(key)) return;
            const meta = files[key] || {};
            const displayName = meta.name || payload[`${key}_name`] || payload[key] || 'Uploaded file';
            showExistingFile(key, displayName, meta.url);
          });
          updatePanelStatuses();
          calculateProfileProgress();
        } catch (_) { /* noop */ }
      }

      function collectCompanyProfile() {
        const form = document.getElementById('companyProfileForm');
        if (!form) return new FormData();
        const data = new FormData();
        const multi = {};
        Array.from(form.querySelectorAll('[name]')).forEach((el) => {
          const key = el.getAttribute('name');
          if (!key) return;
          if (el.dataset.multi === 'true') {
            if (!multi[key]) multi[key] = [];
            if (el.checked) multi[key].push(el.value);
            return;
          }
          if (el.type === 'radio') {
            if (el.checked) data.append(key, el.value || '');
            return;
          }
          if (el.type === 'checkbox') {
            data.append(key, el.checked ? 'true' : 'false');
          } else if (el.type === 'file') {
            if (el.files && el.files.length) {
              Array.from(el.files).forEach((file) => data.append(key, file));
            }
          } else if (el.multiple && el.tagName === 'SELECT') {
            const selected = Array.from(el.selectedOptions).map((o) => o.value).filter(Boolean);
            data.append(key, selected.join(','));
          } else {
            data.append(key, el.value || '');
          }
        });
        Object.entries(multi).forEach(([key, values]) => {
          data.append(key, values.join(','));
        });
        return data;
      }

      async function saveCompanyProfile(panelKey) {
        const mainBtn = document.getElementById('saveCompanyProfile');
        const status = document.getElementById('companyProfileStatus');
        
        // Find the section button if panelKey provided
        let sectionBtn = null;
        let sectionMeta = null;
        if (panelKey) {
          sectionBtn = document.querySelector(`[data-panel-key="${panelKey}"]`);
          sectionMeta = document.querySelector(`[data-panel-save="${panelKey}"]`);
        }
        
        // Disable buttons and show loading state
        if (status) status.textContent = '';
        if (mainBtn) mainBtn.disabled = true;
        if (sectionBtn) {
          sectionBtn.disabled = true;
          sectionBtn.textContent = 'Saving...';
        }
        
        try {
          const payload = collectCompanyProfile();
          const res = await fetch('/api/company-profile', {
            method: 'POST',
            credentials: 'include',
            headers: { 'X-CSRF-Token': getCSRF() },
            body: payload,
          });
          if (!res.ok) throw new Error('Save failed');
          
          // Show success
          if (status) status.textContent = 'Company profile saved.';
          if (sectionMeta) sectionMeta.textContent = 'Saved just now';
          
          if (panelKey) {
            recordPanelSave(panelKey);
          } else {
            recordAllPanelSaves();
          }
          
          // Reload profile to reflect uploaded files
          await loadCompanyProfile();
          
        } catch (_) {
          if (status) status.textContent = 'Could not save company profile.';
          if (sectionMeta) sectionMeta.textContent = 'Save failed';
        } finally {
          if (mainBtn) mainBtn.disabled = false;
          if (sectionBtn) {
            sectionBtn.disabled = false;
            sectionBtn.textContent = 'Save this section';
          }
        }
      }

      document.getElementById('saveCompanyProfile')?.addEventListener('click', () => saveCompanyProfile());
      document.getElementById('resetCompanyProfile')?.addEventListener('click', loadCompanyProfile);

      function bindFilePreviews() {
        document.querySelectorAll('.company-profile-section input[type="file"]').forEach((input) => {
          if (input.dataset.boundChange === '1') return;
          input.dataset.boundChange = '1';
          input.addEventListener('change', () => {
            const file = input.files?.[0];
            if (file) {
              markFileSelection(input, file.name);
            }
          });
        });
      }

      function addPanelSaveButtons() {
        document.querySelectorAll('.company-profile-section .profile-panel').forEach((panel, idx) => {
          if (panel.querySelector('.panel-save-actions')) return;
          const content = panel.querySelector('.panel-content');
          if (!content) return;
          const wrapper = document.createElement('div');
          wrapper.className = 'panel-save-actions';
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'btn-primary';
          btn.textContent = 'Save this section';
          const key = (panel.querySelector('.panel-title h3')?.textContent || `panel-${idx + 1}`)
            .toLowerCase()
            .replace(/\s+/g, '-')
            .replace(/[^a-z0-9\-]/g, '');
          btn.dataset.panelKey = key;
          const meta = document.createElement('span');
          meta.className = 'panel-save-meta';
          meta.setAttribute('data-panel-save', key);
          const savedMap = loadPanelSaveTimes();
          if (savedMap[key]) {
            meta.textContent = `Last saved ${formatSaveTime(savedMap[key])}`;
          }
          btn.addEventListener('click', () => saveCompanyProfile(key));
          wrapper.appendChild(btn);
          wrapper.appendChild(meta);
          content.appendChild(wrapper);
        });
        updatePanelStatuses();
      }

      // Dynamic repeatables for references and subcontractors
      let referenceCount = document.querySelectorAll('#referencesContainer .reference-entry').length || 1;
      let subCount = document.querySelectorAll('#subcontractorList .subcontractor-entry').length || 1;

      function addReference() {
        const container = document.getElementById('referencesContainer');
        if (!container) return;
        const current = container.querySelectorAll('.reference-entry').length;
        if (current >= 5) {
          alert('Maximum of 5 references.');
          return;
        }
        const n = current + 1;
        referenceCount = n;
        const entry = document.createElement('div');
        entry.className = 'reference-entry';
        entry.dataset.index = n;
        entry.innerHTML = `
          <div class="reference-header">
            <h4>Reference #${n}</h4>
            <button type="button" class="remove-btn" onclick="removeReference(this)">Remove</button>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Business Name <span class="required">*</span></label>
              <input type="text" name="ref${n}_business" class="form-input" placeholder="Client company name">
            </div>
            <div class="form-group">
              <label>Contact Name <span class="required">*</span></label>
              <input type="text" name="ref${n}_contact" class="form-input" placeholder="Contact person">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Title</label>
              <input type="text" name="ref${n}_title" class="form-input" placeholder="Job title">
            </div>
            <div class="form-group">
              <label>Email <span class="required">*</span></label>
              <input type="email" name="ref${n}_email" class="form-input" placeholder="contact@company.com">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Phone <span class="required">*</span></label>
              <input type="tel" name="ref${n}_phone" class="form-input" placeholder="(xxx) xxx-xxxx">
            </div>
            <div class="form-group">
              <label>Address</label>
              <input type="text" name="ref${n}_address" class="form-input" placeholder="City, State">
            </div>
          </div>
          <div class="form-group">
            <label>Project / Contract Description <span class="required">*</span></label>
            <textarea class="form-textarea" name="ref${n}_description" rows="2" placeholder="Brief description of work performed..."></textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Contract Amount</label>
              <input type="text" name="ref${n}_amount" class="form-input" placeholder="$XXX,XXX (optional)">
            </div>
            <div class="form-group">
              <label>Contract Dates</label>
              <input type="text" name="ref${n}_dates" class="form-input" placeholder="MM/YYYY - MM/YYYY">
            </div>
          </div>
          <div class="form-group">
            <label>Reference Letter</label>
            <div class="file-upload-area small">
              <input type="file" name="ref${n}_letter" id="ref${n}_letter" accept=".pdf,.jpg,.png,.docx" hidden>
              <label class="file-upload-label small" for="ref${n}_letter">
                <span class="upload-text">Upload letter (optional)</span>
              </label>
            </div>
          </div>
        `;
        const removeBtn = entry.querySelector('.remove-btn');
        if (n === 1 && removeBtn) {
          removeBtn.style.display = 'none';
        }
        entry.querySelectorAll('input, textarea, select').forEach((el) => {
          el.addEventListener('input', updatePanelStatuses);
          el.addEventListener('change', updatePanelStatuses);
        });
        container.appendChild(entry);
        upgradeFileInputs();
        bindFilePreviews();
        bindFileReplaceButtons();
        updatePanelStatuses();
      }

      function removeReference(btn) {
        const entry = btn.closest('.reference-entry');
        const container = document.getElementById('referencesContainer');
        if (!entry || !container) return;
        entry.remove();
        const remaining = container.querySelectorAll('.reference-entry').length;
        if (remaining === 0) {
          referenceCount = 0;
          addReference();
        } else {
          updatePanelStatuses();
        }
      }

      function removeSubcontractor(btn) {
        const entry = btn.closest('.subcontractor-entry');
        const container = document.getElementById('subcontractorList');
        if (!entry || !container) return;
        entry.remove();
        const remaining = container.querySelectorAll('.subcontractor-entry').length;
        if (remaining === 0) {
          subCount = 0;
          addSubcontractor();
        } else {
          updatePanelStatuses();
        }
      }

      function addSubcontractor() {
        const container = document.getElementById('subcontractorList');
        if (!container) return;
        const current = container.querySelectorAll('.subcontractor-entry').length;
        const n = current + 1;
        subCount = n;
        const card = createSubcontractorCard(n);
        container.appendChild(card);
        upgradeFileInputs();
        bindFilePreviews();
        bindFileReplaceButtons();
        updatePanelStatuses();
      }

      // expose reference handlers for inline buttons
      window.addReference = addReference;
      window.removeReference = removeReference;
      window.removeSubcontractor = removeSubcontractor;
      window.addSubcontractor = addSubcontractor;

            function createSubcontractorCard(n) {
        const wrapper = document.createElement('div');
        wrapper.className = 'repeatable-card subcontractor-entry';
        wrapper.dataset.index = n;
        wrapper.innerHTML = `
          <div class="subcontractor-header reference-header">
            <h4>Subcontractor #${n}</h4>
            <button type="button" class="remove-btn" onclick="removeSubcontractor(this)">Remove</button>
          </div>
          <div class="form-row three-col">
            <div class="form-group">
              <label>Subcontractor Business Name</label>
              <input type="text" name="sub${n}_name" class="form-input">
            </div>
            <div class="form-group">
              <label>Contact Person</label>
              <input type="text" name="sub${n}_contact" class="form-input">
            </div>
            <div class="form-group">
              <label>Email</label>
              <input type="email" name="sub${n}_email" class="form-input">
            </div>
          </div>
          <div class="form-row three-col">
            <div class="form-group">
              <label>Phone</label>
              <input type="tel" name="sub${n}_phone" class="form-input">
            </div>
            <div class="form-group">
              <label>Address</label>
              <input type="text" name="sub${n}_address" class="form-input">
            </div>
            <div class="form-group">
              <label>Work Performed / Scope</label>
              <input type="text" name="sub${n}_scope" class="form-input">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Contract Compliance Certification Number (if applicable)</label>
              <input type="text" name="sub${n}_compliance" class="form-input">
            </div>
            <div class="form-group">
              <label>Upload - Subcontractor Compliance Certificate (optional)</label>
              <div class="file-upload-area">
                <input type="file" name="sub${n}_certificate" id="upload-sub${n}_certificate" class="form-input file-input" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" hidden>
                <label for="upload-sub${n}_certificate" class="file-upload-label">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                  <span class="upload-text">Upload compliance certificate</span>
                  <span class="upload-hint">PDF, JPG, PNG, DOCX (max 25MB)</span>
                </label>
              </div>
            </div>
          </div>
        `;
        if (n === 1) {
          const removeBtn = wrapper.querySelector('.remove-btn');
          if (removeBtn) removeBtn.style.display = 'none';
        }
        wrapper.querySelectorAll('input, textarea, select').forEach((el) => {
          el.addEventListener('input', updatePanelStatuses);
          el.addEventListener('change', updatePanelStatuses);
        });
        return wrapper;
      }
(function bindRepeatables() {
        document.getElementById('addReferenceBtn')?.addEventListener('click', addReference);

        document.getElementById('addSubcontractorBtn')?.addEventListener('click', addSubcontractor);
      })();

      // Bind actions
      document.getElementById('qaEditProfile')?.addEventListener('click', () => {
        document.querySelector('[data-tab=\"profile\"]')?.click();
      });
      document.getElementById('qaInviteMember')?.addEventListener('click', inviteFlow);
      document.getElementById('qaUpdatePayment')?.addEventListener('click', async () => {
        try {
          const res = await fetch('/billing/portal', { credentials: 'include' });
          if (!res.ok) throw new Error();
          const data = await res.json();
          if (data?.url) {
            window.open(data.url, '_blank', 'noopener');
          } else {
            alert('Could not open Stripe portal right now.');
          }
        } catch (_) {
          alert('Could not open Stripe portal right now.');
        }
      });
      document.getElementById('qaExportData')?.addEventListener('click', () => window.location.href = '/billing');
      document.getElementById('teamInviteBtn')?.addEventListener('click', inviteFlow);
      document.getElementById('teamInviteCardBtn')?.addEventListener('click', inviteFlow);

      // Billing summary (Stripe) in /account Billing tab
      let billingLoaded = false;
      const formatMoney = (amount, currency) => {
        if (amount == null) return '';
        const amt = (Number(amount) || 0) / 100;
        try {
          return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: (currency || 'USD').toUpperCase(),
            minimumFractionDigits: 2,
          }).format(amt);
        } catch (_) {
          return `$${amt.toFixed(2)}`;
        }
      };
      const formatDate = (val) => {
        if (!val) return '';
        try {
          const dt = typeof val === 'number' ? new Date(val * 1000) : new Date(val);
          return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
        } catch (_) {
          return String(val);
        }
      };
      const renderBillingPlan = (data) => {
        const tier = (data?.tier || '').trim() || 'Professional';
        const invoices = data?.invoices || [];
        const latest = invoices[0] || null;
        const price = latest ? formatMoney(latest.amount_paid ?? latest.amount_due, latest.currency) : '$--';
        const cycle = 'Monthly';
        const annualCost = latest ? formatMoney(((latest.amount_paid ?? latest.amount_due) || 0) * 12, latest.currency) : '$--';
        const nextBilling = data?.next_billing_at ? formatDate(data.next_billing_at) : '--';
        const map = {
          starter: 'Starter',
          professional: 'Professional',
          enterprise: 'Enterprise',
        };
        const friendlyTier = map[tier.toLowerCase()] || tier;
        const planNameEl = document.getElementById('billingPlanName');
        const priceEl = document.getElementById('billingPlanPrice');
        const periodEl = document.getElementById('billingPlanPeriod');
        const annualEl = document.getElementById('billingAnnualCost');
        const nextEl = document.getElementById('billingNextBilling');
        const cycleEl = document.getElementById('billingCycle');
        const topTier = document.getElementById('topTierLabel');
        const planBadgeWrap = document.getElementById('planBadge');
        const planBadge = document.getElementById('planBadgeLabel');
        const planName = document.getElementById('planName');
        const planPrice = document.getElementById('planPrice');
        const planPeriod = document.getElementById('planPeriod');
        if (planNameEl) planNameEl.textContent = friendlyTier;
        if (priceEl) priceEl.textContent = price;
        if (periodEl) periodEl.textContent = '/month';
        if (annualEl) annualEl.textContent = annualCost;
        if (nextEl) nextEl.textContent = nextBilling;
        if (cycleEl) cycleEl.textContent = cycle;
        if (topTier) topTier.textContent = friendlyTier;
        if (planBadgeWrap) planBadgeWrap.style.display = friendlyTier ? 'inline-flex' : 'none';
        if (planBadge) planBadge.textContent = friendlyTier;
        if (planName) planName.textContent = friendlyTier;
        if (planPrice) planPrice.textContent = price;
        if (planPeriod) planPeriod.textContent = '/month';
      };
      const openBillingPortal = async () => {
        try {
          const res = await fetch('/billing/portal', { credentials: 'include' });
          if (!res.ok) throw new Error();
          const data = await res.json();
          if (data?.url) window.open(data.url, '_blank', 'noopener');
        } catch (_) {
          alert('Could not open subscription management right now.');
        }
      };
      const renderPaymentMethod = (pmInfo) => {
        const container = document.getElementById('billingPaymentMethods');
        if (!container) return;
        if (!pmInfo || (!pmInfo.brand && !pmInfo.last4)) {
          container.innerHTML = '<div class="muted">No payment method on file.</div>';
          return;
        }
        const { brand, last4, exp_month, exp_year } = pmInfo;
        const exp = exp_month && exp_year ? `Expires ${String(exp_month).padStart(2, '0')}/${String(exp_year).slice(-2)}` : '';
        container.innerHTML = `
          <div class="payment-card active">
            <div class="payment-card-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
                <rect x="1" y="4" width="22" height="16" rx="3" fill="#1A1F71"></rect>
                <text x="12" y="14" text-anchor="middle" fill="white" font-size="6" font-weight="bold">${(brand || 'CARD').toUpperCase()}</text>
              </svg>
            </div>
            <div class="payment-card-info">
              <span class="payment-card-number">**** **** **** ${last4 || ''}</span>
              <span class="payment-card-expiry">${exp}</span>
            </div>
            <span class="payment-card-default">Default</span>
            <button class="payment-card-edit" id="billingPortalBtn">Edit</button>
          </div>
          <button class="add-payment-btn" id="billingPortalAddBtn">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            Manage Payment Methods
          </button>
        `;
        document.getElementById('billingPortalBtn')?.addEventListener('click', openBillingPortal);
        document.getElementById('billingPortalAddBtn')?.addEventListener('click', openBillingPortal);
      };
      const renderInvoices = (invoices) => {
        const body = document.getElementById('billingHistoryRows');
        if (!body) return;
        if (!invoices || !invoices.length) {
          body.innerHTML = '<div class="billing-row"><span class="muted">No invoices yet.</span></div>';
          return;
        }
        body.innerHTML = invoices.map((inv) => {
          const created = formatDate(inv.created || inv.period_end);
          const desc = inv.description || 'Subscription';
          const amt = formatMoney(inv.amount_paid ?? inv.amount_due, inv.currency);
          const status = (inv.status || '').toLowerCase();
          const statusCls = status === 'paid' ? 'paid' : '';
          const url = inv.hosted_invoice_url || inv.invoice_pdf;
          const downloadBtn = url ? `
            <a class="download-btn" href="${url}" target="_blank" rel="noopener" aria-label="Download invoice">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </a>` : '';
          return `
            <div class="billing-row">
              <span>${created}</span>
              <span>${desc}</span>
              <span>${amt}</span>
              <span class="status-badge ${statusCls}">${status ? status.charAt(0).toUpperCase() + status.slice(1) : ''}</span>
              ${downloadBtn}
            </div>
          `;
        }).join('');
      };
      const loadBillingSummary = async () => {
        if (billingLoaded) return;
        billingLoaded = true;
        try {
          const res = await fetch('/api/billing/summary', { credentials: 'include' });
          if (!res.ok) throw new Error();
          const data = await res.json();
          renderBillingPlan(data);
          renderPaymentMethod(data?.payment_method);
          renderInvoices(data?.invoices || []);
        } catch (_) {
          const pm = document.getElementById('billingPaymentMethods');
          const inv = document.getElementById('billingHistoryRows');
          if (pm) pm.innerHTML = '<div class="muted">Could not load payment method.</div>';
          if (inv) inv.innerHTML = '<div class="billing-row"><span class="muted">Could not load invoices.</span></div>';
        }
      };

      // Trigger billing load when tab is opened
      document.querySelector('[data-tab=\"billing\"]')?.addEventListener('click', () => {
        loadBillingSummary();
      });
      // Also load eagerly for logged-in users
      loadBillingSummary();
      document.getElementById('billingManageBtn')?.addEventListener('click', openBillingPortal);

      // Help dropdown toggle (match shared layout)
      (function(){
        const btn = document.getElementById('help-btn');
        const menu = document.getElementById('help-menu');
        if (!btn || !menu) return;
        const toggle = (open) => {
          menu.style.display = open ? 'block' : 'none';
          btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        };
        btn.addEventListener('click', function(){
          const isOpen = menu.style.display === 'block';
          toggle(!isOpen);
        });
        document.addEventListener('click', function(e){
          if (!btn.contains(e.target) && !menu.contains(e.target)) toggle(false);
        });
      })();

      // Avatar dropdown toggle (match shared layout)
      (function(){
        const btn = document.getElementById('avatar-btn');
        const menu = document.getElementById('avatar-menu');
        if (!btn || !menu) return;
        const toggle = (open) => {
          menu.style.display = open ? 'block' : 'none';
          btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        };
        btn.addEventListener('click', function(){
          const isOpen = menu.style.display === 'block';
          toggle(!isOpen);
        });
        document.addEventListener('click', function(e){
          if (!btn.contains(e.target) && !menu.contains(e.target)) toggle(false);
        });
      })();

      // Avatar Upload Logic
      (function initAvatarUpload() {
        const modal = document.getElementById('avatarModal');
        const editBtn = document.querySelector('.avatar-edit-btn');
        const closeBtn = document.getElementById('avatarModalClose');
        const cancelBtn = document.getElementById('avatarCancelBtn');
        const saveBtn = document.getElementById('avatarSaveBtn');
        const fileInput = document.getElementById('avatarFileInput');
        const dropZone = document.getElementById('avatarDropZone');
        const placeholder = document.getElementById('uploadPlaceholder');
        const cropContainer = document.getElementById('cropContainer');
        const cropImage = document.getElementById('cropImage');
        const cropZoom = document.getElementById('cropZoom');
        
        let currentFile = null;
        let imgPosition = { x: 0, y: 0 };
        let isDragging = false;
        let dragStart = { x: 0, y: 0 };
        let baseScale = 1; // Scale to fit image in wrapper

        // Open modal
        editBtn?.addEventListener('click', () => {
          modal.style.display = 'flex';
          resetCropper();
        });

        // Close modal
        function closeModal() {
          modal.style.display = 'none';
          resetCropper();
        }
        closeBtn?.addEventListener('click', closeModal);
        cancelBtn?.addEventListener('click', closeModal);
        modal?.addEventListener('click', (e) => {
          if (e.target === modal) closeModal();
        });

        // File selection
        dropZone?.addEventListener('click', (e) => {
          if (!cropContainer.style.display || cropContainer.style.display === 'none') {
            fileInput.click();
          }
        });

        fileInput?.addEventListener('change', (e) => {
          if (e.target.files?.[0]) handleFile(e.target.files[0]);
        });

        // Drag and drop
        ['dragenter', 'dragover'].forEach(evt => {
          dropZone?.addEventListener(evt, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
          });
        });

        ['dragleave', 'drop'].forEach(evt => {
          dropZone?.addEventListener(evt, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
          });
        });

        dropZone?.addEventListener('drop', (e) => {
          const file = e.dataTransfer?.files?.[0];
          if (file && file.type.startsWith('image/')) handleFile(file);
        });

        function handleFile(file) {
          if (file.size > 5 * 1024 * 1024) {
            alert('File too large. Maximum size is 5MB.');
            return;
          }
          currentFile = file;
          const reader = new FileReader();
          reader.onload = (e) => {
            cropImage.src = e.target.result;
            cropImage.onload = () => {
              placeholder.style.display = 'none';
              cropContainer.style.display = 'block';
              saveBtn.disabled = false;
              centerImage();
            };
          };
          reader.readAsDataURL(file);
        }

        function centerImage() {
          const wrapper = cropImage.parentElement;
          const wrapperSize = Math.min(wrapper.offsetWidth, wrapper.offsetHeight);
          const imgW = cropImage.naturalWidth;
          const imgH = cropImage.naturalHeight;
          
          const minDimension = Math.min(imgW, imgH);
          const maxDimension = Math.max(imgW, imgH);
          
          // Base scale so the smallest dimension fills the 200px crop circle
          baseScale = 200 / minDimension;
          
          // Also ensure the image fits inside the wrapper at min zoom
          const fitInWrapper = wrapperSize / maxDimension;
          if (baseScale < fitInWrapper) {
            baseScale = fitInWrapper;
          }
          
          // Reset zoom (1x now means baseScale)
          cropZoom.value = 1;
          
          const scale = baseScale * parseFloat(cropZoom.value);
          const scaledW = imgW * scale;
          const scaledH = imgH * scale;
          imgPosition.x = (wrapper.offsetWidth - scaledW) / 2;
          imgPosition.y = (wrapper.offsetHeight - scaledH) / 2;
          updateImageTransform();
        }

        function updateImageTransform() {
          const zoom = parseFloat(cropZoom.value);
          const scale = baseScale * zoom;
          cropImage.style.width = cropImage.naturalWidth * scale + 'px';
          cropImage.style.height = cropImage.naturalHeight * scale + 'px';
          cropImage.style.left = imgPosition.x + 'px';
          cropImage.style.top = imgPosition.y + 'px';
        }

        cropZoom?.addEventListener('input', updateImageTransform);

        // Drag to pan image
        cropImage?.addEventListener('mousedown', (e) => {
          isDragging = true;
          dragStart = { x: e.clientX - imgPosition.x, y: e.clientY - imgPosition.y };
          e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
          if (!isDragging) return;
          imgPosition.x = e.clientX - dragStart.x;
          imgPosition.y = e.clientY - dragStart.y;
          updateImageTransform();
        });

        document.addEventListener('mouseup', () => isDragging = false);

        function resetCropper() {
          currentFile = null;
          fileInput.value = '';
          cropImage.src = '';
          cropZoom.value = 1;
          placeholder.style.display = 'block';
          cropContainer.style.display = 'none';
          saveBtn.disabled = true;
          imgPosition = { x: 0, y: 0 };
          baseScale = 1;
        }

        // Save - crop and upload
        saveBtn?.addEventListener('click', async () => {
          if (!currentFile) return;
          saveBtn.disabled = true;
          saveBtn.textContent = 'Uploading...';

          try {
            // Create cropped canvas
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const size = 200; // Output size
            canvas.width = size;
            canvas.height = size;

            const wrapper = cropImage.parentElement;
            const scale = baseScale * parseFloat(cropZoom.value);
            const wrapperCenterX = wrapper.offsetWidth / 2;
            const wrapperCenterY = wrapper.offsetHeight / 2;

            // Calculate source coordinates
            const srcX = (wrapperCenterX - imgPosition.x - size / 2) / scale;
            const srcY = (wrapperCenterY - imgPosition.y - size / 2) / scale;
            const srcSize = size / scale;

            ctx.drawImage(cropImage, srcX, srcY, srcSize, srcSize, 0, 0, size, size);

            // Convert to blob
            const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
            const formData = new FormData();
            formData.append('avatar', blob, 'avatar.jpg');

            const res = await fetch('/api/account/avatar', {
              method: 'POST',
              body: formData,
              credentials: 'include',
              headers: { 'X-CSRF-Token': getCSRF() },
            });
            const data = await res.json();

            if (data.ok && data.avatar_url) {
              // Update UI
              const largeAvatar = document.getElementById('avatarInitials');
              largeAvatar.classList.add('has-image');
              let img = largeAvatar.querySelector('img');
              if (!img) {
                img = document.createElement('img');
                largeAvatar.insertBefore(img, largeAvatar.firstChild);
              }
              img.src = data.avatar_url;

              // Update top avatar too
              const topAvatar = document.getElementById('topAvatar');
              if (topAvatar) {
                topAvatar.innerHTML = `<img src=\"${data.avatar_url}\" style=\"width:100%;height:100%;object-fit:cover;border-radius:50%;\">`;
              }
              closeModal();
            } else {
              alert(data.detail || 'Upload failed');
            }
          } catch (err) {
            alert('Upload failed: ' + err.message);
          } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Photo';
          }
        });
      })();

      document.getElementById('savePersonalInfo')?.addEventListener('click', savePersonalInfo);
      document.getElementById('resetPersonalInfo')?.addEventListener('click', () => {
        resetPersonalInfo();
        loadPersonalDraft(true);
      });
      document.querySelectorAll('#profileFirstName, #profileLastName, #profileEmail, #profilePhone, #profileJobTitle').forEach((el) => {
        el.addEventListener('input', () => savePersonalDraft(personalFormValues()));
      });
      document.getElementById('saveAlertPrefs')?.addEventListener('click', saveAlertPreferences);
      upgradeFileInputs();
      bindFileReplaceButtons();
      bindFilePreviews();
      addPanelSaveButtons();
      initSubAccordions();
      initQuickSetupWizard();
      document.querySelectorAll('.company-profile-section input, .company-profile-section textarea, .company-profile-section select').forEach((el) => {
        el.addEventListener('input', updatePanelStatuses);
        el.addEventListener('change', updatePanelStatuses);
      });
      let progressTimeout;
      document.getElementById('companyProfileForm')?.addEventListener('input', () => {
        clearTimeout(progressTimeout);
        progressTimeout = setTimeout(calculateProfileProgress, 500);
      });

      handleHashNavigation();
      bindTeamHandlers();
      loadAccount();
      loadCompanyProfile();
    });
  