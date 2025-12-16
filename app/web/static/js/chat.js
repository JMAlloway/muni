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
    chatEls.messages.innerHTML = chatHistory
      .map(
        (msg) => `
      <div class="chat-message ${msg.role}">
        <div class="chat-bubble">${escapeHtml(msg.content)}</div>
      </div>
    `
      )
      .join("");
    chatEls.messages.scrollTop = chatEls.messages.scrollHeight;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  async function sendMessage() {
    const sessionId = getSessionId();
    const message = chatEls.input?.value.trim();
    if (!sessionId || !message) return;

    chatHistory.push({ role: "user", content: message });
    renderMessages();
    if (chatEls.input) chatEls.input.value = "";
    if (chatEls.sendBtn) chatEls.sendBtn.disabled = true;

    const typingEl = document.createElement("div");
    typingEl.className = "chat-message assistant typing";
    typingEl.innerHTML = '<div class="chat-bubble">Thinking...</div>';
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
        chatHistory.push({ role: "assistant", content: data.content });
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
