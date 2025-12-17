(function () {
  const chatEls = {
    sidebar: document.getElementById("chatSidebar"),
    messages: document.getElementById("chatMessages"),
    input: document.getElementById("chatInput"),
    sendBtn: document.getElementById("chatSend"),
    toggleBtn: document.getElementById("toggleChat"),
    openBtn: document.getElementById("openChatBtn"),
  };

  let chatHistory = [];
  const userAvatarUrl =
    window.currentUserAvatar ||
    (() => {
      const img = document.querySelector(".avatar-circle img, #topAvatar img");
      return img ? img.src : null;
    })();

  function getCsrf() {
    return document.getElementById("csrfTokenField")?.value || "";
  }

  function getSessionId() {
    return window.aiStudioState?.sessionId || null;
  }

  function enableChat(enabled) {
    if (chatEls.input) chatEls.input.disabled = !enabled;
    if (chatEls.sendBtn) chatEls.sendBtn.disabled = !enabled;
    if (!enabled && chatEls.messages) {
      chatEls.messages.innerHTML = '<div class="chat-empty">Ask a question about the RFP...</div>';
    }
  }

  async function loadChatHistory(sessionId) {
    if (!sessionId || !chatEls.messages) return;
    try {
      const res = await fetch(`/api/chat/${sessionId}/messages`, {
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (res.ok) {
        chatHistory = await res.json();
        renderMessages();
      }
    } catch (e) {
      console.error("Failed to load chat history:", e);
    }
  }

  function renderMessages() {
    if (!chatEls.messages) return;
    if (chatHistory.length === 0) {
      chatEls.messages.innerHTML = '<div class="chat-empty">Ask a question about the RFP...</div>';
      return;
    }
    chatEls.messages.innerHTML = chatHistory.map(renderMessage).join("");
    chatEls.messages.scrollTop = chatEls.messages.scrollHeight;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  function formatMessageContent(text) {
    const escaped = escapeHtml(text || "");
    const lines = escaped.split(/\n/);
    const html = [];
    let buffer = [];
    let inList = false;

    const flushParagraph = () => {
      if (buffer.length) {
        html.push(`<p>${buffer.join("<br>")}</p>`);
        buffer = [];
      }
    };

    const closeList = () => {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
    };

    for (const rawLine of lines) {
      const line = rawLine.trim();

      // Blank line -> paragraph break
      if (!line) {
        closeList();
        flushParagraph();
        continue;
      }

      // Bullet list detection
      if (/^[-*•]\s+/.test(line)) {
        flushParagraph();
        if (!inList) {
          html.push('<ul class="chat-list">');
          inList = true;
        }
        html.push(`<li>${line.replace(/^[-*•]\s+/, "")}</li>`);
        continue;
      }

      // Regular text
      closeList();
      buffer.push(line);
    }

    closeList();
    flushParagraph();

    return html.join("") || escaped;
  }

  function initialsFor(name) {
    return (
      name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((n) => n[0].toUpperCase())
        .join("") || "AI"
    );
  }

  function formatTimestamp(ts) {
    if (!ts) return "";
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function renderMessage(msg) {
    const isUser = msg.role === "user";
    const author = isUser ? "You" : "AI Assistant";
    const avatarClass = isUser ? "blue" : "purple";
    const time = formatTimestamp(msg.created_at);
    const content = formatMessageContent(msg.content);
    const avatar = isUser && userAvatarUrl
      ? `<div class="drawer-msg-avatar"><img src="${userAvatarUrl}" alt="${author}"></div>`
      : `<div class="drawer-msg-avatar ${avatarClass}">${initialsFor(author)}</div>`;

    return `
      <div class="drawer-message chat-thread ${isUser ? "own" : "assistant"}">
        ${avatar}
        <div class="drawer-msg-content">
          <div class="drawer-msg-header">
            <span class="drawer-msg-author">${author}</span>
            ${time ? `<span class="drawer-msg-time">${time}</span>` : ""}
          </div>
          <div class="drawer-msg-text">${content}</div>
        </div>
      </div>
    `;
  }

  async function sendMessage() {
    const sessionId = getSessionId();
    const message = chatEls.input?.value.trim();
    if (!sessionId || !message) return;

    const now = new Date().toISOString();
    chatHistory.push({ role: "user", content: message, created_at: now });
    renderMessages();
    if (chatEls.input) chatEls.input.value = "";
    if (chatEls.sendBtn) chatEls.sendBtn.disabled = true;

    const typingEl = document.createElement("div");
    typingEl.className = "drawer-message chat-thread assistant typing";
    typingEl.innerHTML = `
      <div class="drawer-msg-avatar purple">AI</div>
      <div class="drawer-msg-content">
        <div class="drawer-msg-header">
          <span class="drawer-msg-author">AI Assistant</span>
          <span class="drawer-msg-time">...</span>
        </div>
        <div class="drawer-msg-text">
          <div class="drawer-typing-dots"><span></span><span></span><span></span></div>
        </div>
      </div>
    `;
    chatEls.messages?.appendChild(typingEl);
    if (chatEls.messages) chatEls.messages.scrollTop = chatEls.messages.scrollHeight;

    try {
      const res = await fetch("/api/chat/message", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrf(),
        },
        body: JSON.stringify({ session_id: sessionId, message }),
      });

      typingEl.remove();

      if (res.ok) {
        const data = await res.json();
        chatHistory.push({ role: "assistant", content: data.content, created_at: data.created_at });
        renderMessages();
      } else {
        let detail = "Failed to get response";
        try {
          const err = await res.json();
          detail = err.detail || JSON.stringify(err);
        } catch (_) {}
        alert(detail || "Failed to send message");
      }
    } catch (e) {
      typingEl.remove();
      console.error("Chat error:", e);
      alert("Failed to send message");
    }
    if (chatEls.sendBtn) chatEls.sendBtn.disabled = false;
  }

  chatEls.sendBtn?.addEventListener("click", sendMessage);
  chatEls.input?.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  chatEls.toggleBtn?.addEventListener("click", () => {
    chatEls.sidebar?.classList.toggle("collapsed");
    if (chatEls.sidebar?.classList.contains("collapsed")) {
      chatEls.openBtn?.classList.add("visible");
    } else {
      chatEls.openBtn?.classList.remove("visible");
    }
  });

  chatEls.openBtn?.addEventListener("click", () => {
    chatEls.sidebar?.classList.remove("collapsed");
    chatEls.openBtn?.classList.remove("visible");
  });

  window.aiChat = {
    enable: enableChat,
    loadHistory: loadChatHistory,
    clear: () => {
      chatHistory = [];
      renderMessages();
    },
  };
})();
