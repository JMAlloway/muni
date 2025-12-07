(function() {
  function initNotifications() {
    const notifBtn = document.getElementById('notifBtn');
    const notifSidebar = document.getElementById('notifSidebar');
    const notifOverlay = document.getElementById('notifOverlay');
    const notifCloseBtn = document.getElementById('notifCloseBtn');
    const markAllRead = document.getElementById('markAllRead');
    const notifTabs = document.querySelectorAll('.notif-tab');
    const notifItems = document.querySelectorAll('.notif-item');

    function openNotifSidebar() {
      if (notifSidebar) {
        notifSidebar.classList.add('active');
        notifOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
      }
    }

    function closeNotifSidebar() {
      if (notifSidebar) {
        notifSidebar.classList.remove('active');
        notifOverlay.classList.remove('active');
        document.body.style.overflow = '';
      }
    }

    if (notifBtn) {
      notifBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        openNotifSidebar();
      });
    }
    
    if (notifCloseBtn) {
      notifCloseBtn.addEventListener('click', closeNotifSidebar);
    }
    
    if (notifOverlay) {
      notifOverlay.addEventListener('click', closeNotifSidebar);
    }

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && notifSidebar && notifSidebar.classList.contains('active')) {
        closeNotifSidebar();
      }
    });

    notifTabs.forEach(tab => {
      tab.addEventListener('click', function() {
        notifTabs.forEach(t => t.classList.remove('active'));
        this.classList.add('active');
        
        const filter = this.dataset.filter;
        notifItems.forEach(item => {
          if (filter === 'all') {
            item.style.display = 'flex';
          } else if (filter === 'unread') {
            item.style.display = item.classList.contains('unread') ? 'flex' : 'none';
          } else {
            item.style.display = item.dataset.type === filter ? 'flex' : 'none';
          }
        });
      });
    });

    if (markAllRead) {
      markAllRead.addEventListener('click', function() {
        notifItems.forEach(item => {
          item.classList.remove('unread', 'urgent');
        });
        const unreadTab = document.querySelector('.notif-tab[data-filter="unread"] .notif-tab-count');
        if (unreadTab) unreadTab.textContent = '0';
        const notifDot = document.querySelector('.notif-dot');
        if (notifDot) notifDot.style.display = 'none';
      });
    }

    document.querySelectorAll('.notif-item-action').forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        const item = this.closest('.notif-item');
        item.style.opacity = '0';
        item.style.transform = 'translateX(20px)';
        setTimeout(() => item.remove(), 200);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNotifications);
  } else {
    initNotifications();
  }
})();
