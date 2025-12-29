(function () {
  const state = {
    notifications: [],
  };

  function getCsrf() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatDateLabel(dateStr) {
    if (!dateStr) return "Recent";
    const d = new Date(dateStr);
    const today = new Date();
    const isToday = d.toDateString() === today.toDateString();
    if (isToday) return "Today";
    const diffDays = Math.floor((today - d) / 86400000);
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return "This Week";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return "";
    const now = Date.now();
    const ts = new Date(dateStr).getTime();
    const diff = Math.max(0, now - ts);
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return new Date(dateStr).toLocaleDateString();
  }

  function iconFor(type) {
    const mapping = {
      deadline: { icon: "⏰", cls: "warning" },
      warning: { icon: "⚠️", cls: "warning" },
      urgent: { icon: "⚡", cls: "urgent" },
      team: { icon: "👥", cls: "team" },
      comment: { icon: "💬", cls: "comment" },
      success: { icon: "✅", cls: "success" },
      info: { icon: "ℹ️", cls: "info" },
    };
    mapping.mention = mapping.urgent;
    mapping.invite_accepted = mapping.success;
    mapping.removed_from_team = mapping.warning;
    mapping.role_changed = mapping.info;
    return mapping[type] || mapping.info;
  }

  function setUnreadCount(count) {
    const unreadTab = document.querySelector('.notif-tab[data-filter="unread"] .notif-tab-count');
    if (unreadTab) unreadTab.textContent = String(count);
    const notifDot = document.querySelector('.notif-dot');
    if (notifDot) notifDot.style.display = count > 0 ? "inline-block" : "none";
  }

  function filterList(filter) {
    document.querySelectorAll(".notif-tab").forEach((t) => t.classList.remove("active"));
    const activeTab = document.querySelector(`.notif-tab[data-filter="${filter}"]`);
    if (activeTab) activeTab.classList.add("active");
    document.querySelectorAll(".notif-item").forEach((item) => {
      const isUnread = item.classList.contains("unread");
      const type = item.dataset.type || "info";
      if (filter === "all") {
        item.style.display = "flex";
      } else if (filter === "unread") {
        item.style.display = isUnread ? "flex" : "none";
      } else {
        item.style.display = type === filter ? "flex" : "none";
      }
    });
  }

  async function markAsRead(id, itemEl) {
    if (!id) return;
    try {
      await fetch(`/api/notifications/${encodeURIComponent(id)}/read`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrf(),
        },
      });
    } catch (e) {
      // ignore failures; UI still updates
    }
    if (itemEl) {
      itemEl.classList.remove("unread", "urgent");
    }
    const unread = document.querySelectorAll(".notif-item.unread").length;
    setUnreadCount(unread);
  }

  async function markAllRead() {
    try {
      await fetch("/api/notifications/read-all", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrf(),
        },
      });
    } catch (e) {
      // ignore; still clear UI for responsiveness
    }
    document.querySelectorAll(".notif-item").forEach((item) => item.classList.remove("unread", "urgent"));
    setUnreadCount(0);
  }

  function renderNotifications() {
    const list = document.getElementById("notifList");
    if (!list) return;
    list.innerHTML = "";

    if (!state.notifications.length) {
      list.innerHTML = '<div class="muted" style="padding:16px 24px;">No notifications yet.</div>';
      setUnreadCount(0);
      return;
    }

    let unreadCount = 0;
    const groups = {};
    state.notifications.forEach((n) => {
      const label = formatDateLabel(n.created_at);
      if (!groups[label]) groups[label] = [];
      groups[label].push(n);
      if (!n.read_at) unreadCount += 1;
    });
    setUnreadCount(unreadCount);

    Object.keys(groups).forEach((label) => {
      const group = document.createElement("div");
      group.className = "notif-date-group";
      const heading = document.createElement("div");
      heading.className = "notif-date-label";
      heading.textContent = label;
      group.appendChild(heading);

      groups[label].forEach((n) => {
        const meta = iconFor((n.type || "").toLowerCase());
        const item = document.createElement("div");
        item.className = `notif-item${n.read_at ? "" : " unread"}${meta.cls === "urgent" ? " urgent" : ""}`;
        item.dataset.type = (n.type || "info").toLowerCase();
        item.dataset.id = n.id;

        const icon = document.createElement("div");
        icon.className = `notif-item-icon ${meta.cls}`;
        icon.textContent = meta.icon;

        const content = document.createElement("div");
        content.className = "notif-item-content";

        const title = document.createElement("div");
        title.className = "notif-item-title";
        title.textContent = n.title || "Notification";

        const desc = document.createElement("div");
        desc.className = "notif-item-desc";
        desc.textContent = n.body || "";

        const metaWrap = document.createElement("div");
        metaWrap.className = "notif-item-meta";
        const time = document.createElement("span");
        time.className = "notif-time";
        time.textContent = formatTimeAgo(n.created_at);
        metaWrap.appendChild(time);

        content.appendChild(title);
        content.appendChild(desc);
        content.appendChild(metaWrap);

        const action = document.createElement("button");
        action.className = "notif-item-action";
        action.type = "button";
        action.title = "Mark as read";
        action.innerHTML = "&times;";

        action.addEventListener("click", (e) => {
          e.stopPropagation();
          markAsRead(n.id, item);
        });

        item.addEventListener("click", () => markAsRead(n.id, item));

        item.appendChild(icon);
        item.appendChild(content);
        item.appendChild(action);
        group.appendChild(item);
      });

      list.appendChild(group);
    });
  }

  async function loadNotifications() {
    const list = document.getElementById("notifList");
    if (list) {
      list.innerHTML = `
        <div class="notif-date-group">
          <div class="notif-date-label">Loading</div>
          <div class="notif-item" data-type="info">
            <div class="notif-item-icon info">⏳</div>
            <div class="notif-item-content">
              <div class="notif-item-title">Loading notifications...</div>
              <div class="notif-item-desc">Please wait</div>
              <div class="notif-item-meta"><span class="notif-time"></span></div>
            </div>
          </div>
        </div>`;
    }

    try {
      const res = await fetch("/api/notifications", { credentials: "include" });
      if (!res.ok) throw new Error(`Failed to load (${res.status})`);
      const data = await res.json();
      state.notifications = Array.isArray(data.notifications) ? data.notifications : [];
    } catch (err) {
      state.notifications = [];
      if (list) {
        list.innerHTML = `<div class="muted" style="padding:16px 24px;">Failed to load notifications.</div>`;
      }
      setUnreadCount(0);
      return;
    }
    renderNotifications();
  }

  function initNotifications() {
    const notifBtn = document.getElementById("notifBtn");
    const notifSidebar = document.getElementById("notifSidebar");
    const notifOverlay = document.getElementById("notifOverlay");
    const notifCloseBtn = document.getElementById("notifCloseBtn");
    const markAllBtn = document.getElementById("markAllRead");
    const notifTabs = document.querySelectorAll(".notif-tab");

    function openNotifSidebar() {
      if (notifSidebar) {
        notifSidebar.classList.add("active");
        if (notifOverlay) notifOverlay.classList.add("active");
        document.body.style.overflow = "hidden";
      }
    }

    function closeNotifSidebar() {
      if (notifSidebar) {
        notifSidebar.classList.remove("active");
        if (notifOverlay) notifOverlay.classList.remove("active");
        document.body.style.overflow = "";
      }
    }

    if (notifBtn) {
      notifBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openNotifSidebar();
      });
    }

    if (notifCloseBtn) {
      notifCloseBtn.addEventListener("click", closeNotifSidebar);
    }

    if (notifOverlay) {
      notifOverlay.addEventListener("click", closeNotifSidebar);
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && notifSidebar && notifSidebar.classList.contains("active")) {
        closeNotifSidebar();
      }
    });

    notifTabs.forEach((tab) => {
      tab.addEventListener("click", function () {
        filterList(this.dataset.filter || "all");
      });
    });

    if (markAllBtn) {
      markAllBtn.addEventListener("click", async function () {
        await markAllRead();
        filterList("all");
      });
    }

    loadNotifications();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initNotifications);
  } else {
    initNotifications();
  }
})();
