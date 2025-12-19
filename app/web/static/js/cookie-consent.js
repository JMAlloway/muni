/**
 * EasyRFP Cookie Consent Manager
 * Manages user cookie preferences and consent banner display
 */

(function() {
  'use strict';

  const CONSENT_COOKIE_NAME = 'cookie_consent';
  const CONSENT_COOKIE_EXPIRY_DAYS = 365;

  // Cookie consent manager
  const CookieConsent = {

    /**
     * Get current consent preferences from cookie
     */
    getPreferences: function() {
      const cookie = this.getCookie(CONSENT_COOKIE_NAME);
      if (!cookie) {
        return null;
      }
      try {
        return JSON.parse(decodeURIComponent(cookie));
      } catch (e) {
        console.error('Failed to parse consent cookie:', e);
        return null;
      }
    },

    /**
     * Save consent preferences
     */
    savePreferences: function(preferences) {
      const value = encodeURIComponent(JSON.stringify(preferences));
      const expires = new Date();
      expires.setDate(expires.getDate() + CONSENT_COOKIE_EXPIRY_DAYS);

      document.cookie = `${CONSENT_COOKIE_NAME}=${value}; expires=${expires.toUTCString()}; path=/; SameSite=Lax`;

      // Apply preferences
      this.applyPreferences(preferences);
    },

    /**
     * Apply consent preferences (enable/disable third-party scripts)
     */
    applyPreferences: function(preferences) {
      // Analytics cookies
      if (preferences.analytics) {
        this.enableAnalytics();
      } else {
        this.disableAnalytics();
      }

      // Marketing cookies (Stripe for payment processing)
      if (preferences.marketing) {
        this.enableMarketing();
      } else {
        this.disableMarketing();
      }

      // Dispatch custom event for other scripts to listen to
      window.dispatchEvent(new CustomEvent('cookieConsentChanged', {
        detail: preferences
      }));
    },

    /**
     * Enable analytics tracking
     */
    enableAnalytics: function() {
      // Placeholder for future analytics integration
      console.log('Analytics enabled');
      window._analyticsEnabled = true;
    },

    /**
     * Disable analytics tracking
     */
    disableAnalytics: function() {
      console.log('Analytics disabled');
      window._analyticsEnabled = false;
    },

    /**
     * Enable marketing cookies (Stripe)
     */
    enableMarketing: function() {
      console.log('Marketing cookies enabled');
      window._marketingEnabled = true;
      // Stripe will be loaded on-demand when user goes to billing page
    },

    /**
     * Disable marketing cookies
     */
    disableMarketing: function() {
      console.log('Marketing cookies disabled');
      window._marketingEnabled = false;
    },

    /**
     * Accept all cookies
     */
    acceptAll: function() {
      const preferences = {
        necessary: true,
        analytics: true,
        marketing: true,
        timestamp: new Date().toISOString()
      };
      this.savePreferences(preferences);
      this.hideBanner();
    },

    /**
     * Reject all optional cookies (keep only necessary)
     */
    rejectAll: function() {
      const preferences = {
        necessary: true,
        analytics: false,
        marketing: false,
        timestamp: new Date().toISOString()
      };
      this.savePreferences(preferences);
      this.hideBanner();
    },

    /**
     * Save custom preferences from settings modal
     */
    saveCustomPreferences: function() {
      const analyticsCheckbox = document.getElementById('cookie-analytics');
      const marketingCheckbox = document.getElementById('cookie-marketing');

      const preferences = {
        necessary: true,
        analytics: analyticsCheckbox ? analyticsCheckbox.checked : false,
        marketing: marketingCheckbox ? marketingCheckbox.checked : false,
        timestamp: new Date().toISOString()
      };

      this.savePreferences(preferences);
      this.hideSettings();
      this.hideBanner();
    },

    /**
     * Show cookie consent banner
     */
    showBanner: function() {
      const banner = document.getElementById('cookieConsentBanner');
      if (banner) {
        banner.classList.add('show');
      }
    },

    /**
     * Hide cookie consent banner
     */
    hideBanner: function() {
      const banner = document.getElementById('cookieConsentBanner');
      if (banner) {
        banner.classList.remove('show');
      }
    },

    /**
     * Show cookie settings modal
     */
    showSettings: function() {
      const modal = document.getElementById('cookieSettingsModal');
      if (modal) {
        // Load current preferences into checkboxes
        const prefs = this.getPreferences() || { analytics: false, marketing: false };

        const analyticsCheckbox = document.getElementById('cookie-analytics');
        const marketingCheckbox = document.getElementById('cookie-marketing');

        if (analyticsCheckbox) analyticsCheckbox.checked = prefs.analytics;
        if (marketingCheckbox) marketingCheckbox.checked = prefs.marketing;

        modal.classList.add('show');
      }
    },

    /**
     * Hide cookie settings modal
     */
    hideSettings: function() {
      const modal = document.getElementById('cookieSettingsModal');
      if (modal) {
        modal.classList.remove('show');
      }
    },

    /**
     * Get cookie value by name
     */
    getCookie: function(name) {
      const nameEQ = name + '=';
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        let cookie = cookies[i];
        while (cookie.charAt(0) === ' ') {
          cookie = cookie.substring(1, cookie.length);
        }
        if (cookie.indexOf(nameEQ) === 0) {
          return cookie.substring(nameEQ.length, cookie.length);
        }
      }
      return null;
    },

    /**
     * Check if user has marketing consent (for Stripe integration)
     */
    hasMarketingConsent: function() {
      const prefs = this.getPreferences();
      return prefs && prefs.marketing === true;
    },

    /**
     * Initialize cookie consent system
     */
    init: function() {
      const self = this;

      // Check if user has already given consent
      const preferences = this.getPreferences();

      if (preferences) {
        // User has already consented, apply their preferences
        this.applyPreferences(preferences);
      } else {
        // Show banner after a short delay
        setTimeout(function() {
          self.showBanner();
        }, 1000);
      }

      // Set up event listeners
      const acceptBtn = document.getElementById('cookieAcceptAll');
      const rejectBtn = document.getElementById('cookieRejectAll');
      const settingsBtn = document.getElementById('cookieSettings');
      const saveSettingsBtn = document.getElementById('cookieSaveSettings');
      const closeSettingsBtn = document.getElementById('cookieCloseSettings');
      const closeSettingsX = document.getElementById('cookieSettingsClose');

      if (acceptBtn) {
        acceptBtn.addEventListener('click', function() {
          self.acceptAll();
        });
      }

      if (rejectBtn) {
        rejectBtn.addEventListener('click', function() {
          self.rejectAll();
        });
      }

      if (settingsBtn) {
        settingsBtn.addEventListener('click', function() {
          self.showSettings();
        });
      }

      if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', function() {
          self.saveCustomPreferences();
        });
      }

      if (closeSettingsBtn) {
        closeSettingsBtn.addEventListener('click', function() {
          self.hideSettings();
        });
      }

      if (closeSettingsX) {
        closeSettingsX.addEventListener('click', function() {
          self.hideSettings();
        });
      }

      // Close modal when clicking outside
      const modal = document.getElementById('cookieSettingsModal');
      if (modal) {
        modal.addEventListener('click', function(e) {
          if (e.target === modal) {
            self.hideSettings();
          }
        });
      }
    }
  };

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      CookieConsent.init();
    });
  } else {
    CookieConsent.init();
  }

  // Expose to window for external access
  window.CookieConsent = CookieConsent;

})();
