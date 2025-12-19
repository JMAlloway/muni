(() => {
  const COOKIE_NAME = "cookie_consent";
  const CONSENT_DAYS = 365;
  const DEFAULT_CONSENT = { necessary: true, analytics: false, marketing: false };

  function getCookie(name) {
    if (!document.cookie) {
      return null;
    }
    const parts = document.cookie.split(";");
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i].trim();
      if (part.startsWith(name + "=")) {
        return decodeURIComponent(part.slice(name.length + 1));
      }
    }
    return null;
  }

  function normalizeConsent(raw) {
    const base = raw && typeof raw === "object" ? raw : {};
    return {
      necessary: true,
      analytics: Boolean(base.analytics),
      marketing: Boolean(base.marketing),
      timestamp: base.timestamp || new Date().toISOString(),
    };
  }

  function readConsent() {
    const raw = getCookie(COOKIE_NAME);
    if (!raw) {
      return null;
    }
    try {
      return normalizeConsent(JSON.parse(raw));
    } catch (err) {
      return null;
    }
  }

  function writeConsent(consent) {
    const normalized = normalizeConsent(consent);
    const expiresAt = new Date(Date.now() + CONSENT_DAYS * 86400000).toUTCString();
    let cookie = `${COOKIE_NAME}=${encodeURIComponent(JSON.stringify(normalized))}; Expires=${expiresAt}; Path=/; SameSite=Lax`;
    if (window.location && window.location.protocol === "https:") {
      cookie += "; Secure";
    }
    document.cookie = cookie;
    return normalized;
  }

  function notifyConsent(consent) {
    try {
      if (typeof window.onCookieConsent === "function") {
        window.onCookieConsent(consent);
      }
    } catch (err) {
      // no-op
    }
    try {
      window.dispatchEvent(new CustomEvent("cookie-consent", { detail: consent }));
    } catch (err) {
      // no-op
    }
  }

  function setConsent(consent) {
    const normalized = writeConsent(consent);
    notifyConsent(normalized);
    return normalized;
  }

  function init() {
    const banner = document.getElementById("cookieConsentBanner");
    const modal = document.getElementById("cookieConsentModal");
    if (!banner || !modal) {
      return;
    }

    const analyticsToggle = document.getElementById("cookieAnalytics");
    const marketingToggle = document.getElementById("cookieMarketing");

    function applyToggles(consent) {
      if (analyticsToggle) {
        analyticsToggle.checked = Boolean(consent.analytics);
      }
      if (marketingToggle) {
        marketingToggle.checked = Boolean(consent.marketing);
      }
    }

    function showBanner() {
      banner.classList.add("is-visible");
      banner.setAttribute("aria-hidden", "false");
    }

    function hideBanner() {
      banner.classList.remove("is-visible");
      banner.setAttribute("aria-hidden", "true");
    }

    function openModal() {
      const current = readConsent() || DEFAULT_CONSENT;
      applyToggles(current);
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("cookie-modal-open");
    }

    function closeModal() {
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("cookie-modal-open");
    }

    function saveFromToggles() {
      return setConsent({
        analytics: analyticsToggle ? analyticsToggle.checked : false,
        marketing: marketingToggle ? marketingToggle.checked : false,
      });
    }

    document.querySelectorAll("[data-consent-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const action = btn.getAttribute("data-consent-action");
        if (action === "accept") {
          setConsent({ analytics: true, marketing: true });
          hideBanner();
          closeModal();
        } else if (action === "reject") {
          setConsent({ analytics: false, marketing: false });
          hideBanner();
          closeModal();
        } else if (action === "customize") {
          openModal();
        } else if (action === "save") {
          saveFromToggles();
          hideBanner();
          closeModal();
        }
      });
    });

    document.querySelectorAll("[data-cookie-close]").forEach((el) => {
      el.addEventListener("click", closeModal);
    });

    document.querySelectorAll("[data-cookie-open]").forEach((el) => {
      el.addEventListener("click", (event) => {
        event.preventDefault();
        openModal();
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeModal();
      }
    });

    const existing = readConsent();
    if (existing) {
      applyToggles(existing);
      notifyConsent(existing);
    } else {
      window.setTimeout(showBanner, 1000);
    }

    window.cookieConsent = {
      get: readConsent,
      set: setConsent,
      open: openModal,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
