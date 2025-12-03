(function() {
  const btn = document.getElementById('notifBtn') || document.getElementById('notif-btn');
  const sidebar = document.getElementById('notifSidebar');
  const overlay = document.getElementById('notifOverlay');
  const closeBtn = document.getElementById('notifCloseBtn');
  const markAllBtn = document.getElementById('markAllRead');
  const tabs = Array.from(document.querySelectorAll('.notif-tab'));
  const listEl = document.getElementById('notifList');
  const badge = document.querySelector('.notif-dot');
  if (!btn || !sidebar || !overlay || !listEl) return;
  listEl.setAttribute('aria-live', 'polite');
  listEl.setAttribute('role', 'region');
  listEl.setAttribute('aria-label', 'Notifications');

  const getCSRF = () => (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
  let items = [];
  let currentFilter = 'all';
  let celebrate = false;

  const timeAgo = (iso) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      const diff = (Date.now() - d.getTime()) / 1000;
      if (diff < 60) return 'Just now';
      if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
      return Math.floor(diff / 86400) + 'd ago';
    } catch (_) {
      return '';
    }
  };

  const dateLabel = (iso) => {
    if (!iso) return 'Earlier';
    const d = new Date(iso);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const thatDay = new Date(d);
    thatDay.setHours(0, 0, 0, 0);
    const diffDays = Math.floor((today - thatDay) / 86400000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1 || diffDays === -1) return 'Yesterday';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  const typeClass = (t = '') => {
    const val = (t || '').toLowerCase();
    if (val.includes('deadline') || val.includes('due')) return 'deadlines urgent';
    if (val.includes('team')) return 'team';
    if (val.includes('warning')) return 'warning';
    if (val.includes('success') || val.includes('won')) return 'success';
    if (val.includes('comment')) return 'comment';
    return 'info';
  };

  const updateBadge = (count) => {
    if (!badge) return;
    if (count > 0) {
      badge.style.display = 'inline-flex';
      badge.textContent = count > 99 ? '99+' : String(count);
      btn.classList.add('has-notifs');
    } else {
      badge.style.display = 'none';
      badge.textContent = '';
      btn.classList.remove('has-notifs');
    }
  };

  const applyFilter = (filter) => {
    currentFilter = filter;
    const countEl = document.querySelector('.notif-tab[data-filter="unread"] .notif-tab-count');
    const allItems = Array.from(listEl.querySelectorAll('.notif-item'));
    allItems.forEach((item) => {
      const type = item.getAttribute('data-type');
      const unread = item.classList.contains('unread');
      let show = true;
      if (filter === 'unread') show = unread;
      else if (filter !== 'all') show = type === filter;
      item.style.display = show ? 'flex' : 'none';
    });
    if (countEl) countEl.textContent = items.filter((n) => !n.read_at).length;
  };

  const render = () => {
    const allRead = !items.some((n) => !n.read_at);
    if (!items.length || (celebrate && allRead)) {
      listEl.innerHTML = `
        <div class="notif-empty celebrate">
          <div class="notif-empty-icon">
            <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="8 12.5 11 15.5 16.5 9.5"></polyline>
            </svg>
          </div>
          <div class="notif-empty-text">
            <div class="notif-empty-title">You’re all caught up</div>
            <div class="notif-empty-sub">We’ll let you know when something new arrives.</div>
          </div>
        </div>`;
      updateBadge(0);
      return;
    }
    const grouped = {};
    items.forEach((n) => {
      const lbl = dateLabel(n.created_at);
      grouped[lbl] = grouped[lbl] || [];
      grouped[lbl].push(n);
    });
    const html = Object.entries(grouped)
      .map(([label, arr]) => {
        const rows = arr
          .map((n) => {
            const unread = !n.read_at;
            const cls = typeClass(n.type);
            const tag = cls.split(' ')[0];
            return `
          <div class="notif-item ${cls} ${unread ? 'unread' : ''}" data-type="${tag}" data-id="${n.id}">
            <div class="notif-item-icon ${tag}">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12" y2="8"></line>
              </svg>
            </div>
            <div class="notif-item-content">
              <div class="notif-item-title">${n.title || ''}</div>
              <div class="notif-item-desc">${n.body || ''}</div>
              <div class="notif-item-meta">
                <span class="notif-time">${timeAgo(n.created_at)}</span>
                <span class="notif-tag ${tag}">${tag.charAt(0).toUpperCase() + tag.slice(1)}</span>
              </div>
            </div>
            <button class="notif-item-action" title="Dismiss" data-dismiss="${n.id}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>`;
          })
          .join('');
        return `<div class="notif-date-group"><div class="notif-date-label">${label}</div>${rows}</div>`;
      })
      .join('');
    listEl.innerHTML = html;
    applyFilter(currentFilter);
    updateBadge(items.filter((n) => !n.read_at).length);
  };

  const load = async () => {
    try {
      const res = await fetch('/api/notifications', { credentials: 'include' });
      if (!res.ok) throw new Error();
      const data = await res.json();
      items = data.notifications || [];
      if (items.some((n) => !n.read_at)) {
        celebrate = false;
      }
      render();
    } catch (err) {
      listEl.innerHTML =
        '<div class="notif-date-group"><div class="notif-item"><div class="notif-item-title">Could not load notifications.</div></div></div>';
    }
  };

  const markRead = async (id) => {
    try {
      await fetch(`/api/notifications/${id}/read`, { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': getCSRF() } });
    } catch (_) {}
  };

  const open = () => {
    sidebar.classList.add('active');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    focusFirst();
  };
  const close = () => {
    sidebar.classList.remove('active');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  };

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    open();
  });
  overlay.addEventListener('click', close);
  closeBtn?.addEventListener('click', close);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar.classList.contains('active')) close();
  });

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      tabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      applyFilter(tab.dataset.filter || 'all');
    });
  });

  markAllBtn?.addEventListener('click', async () => {
    const unread = items.filter((n) => !n.read_at);
    items = items.map((n) => ({ ...n, read_at: n.read_at || new Date().toISOString() }));
    celebrate = true;
    render();
    await Promise.all(unread.map((n) => markRead(n.id)));
  });

  listEl.addEventListener('click', async (e) => {
    const dismiss = e.target.closest('[data-dismiss]');
    if (dismiss) {
      const id = dismiss.getAttribute('data-dismiss');
      items = items.filter((n) => n.id !== id);
      render();
      await markRead(id);
    }
  });

  const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex=\"-1\"])';
  const focusFirst = () => {
    const focusables = sidebar.querySelectorAll(focusableSelector);
    if (focusables.length) focusables[0].focus();
  };
  document.addEventListener('keydown', (e) => {
    if (!sidebar.classList.contains('active')) return;
    if (e.key === 'Tab') {
      const focusables = Array.from(sidebar.querySelectorAll(focusableSelector)).filter(
        (el) => !el.hasAttribute('disabled')
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  load();
})();
