/**
 * Toast Notification System
 * Modern, accessible toast notifications for EasyRFP
 */

const Toast = (function() {
    let container = null;

    const icons = {
        success: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>`,
        error: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>`,
        warning: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>`,
        info: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>`
    };

    function getContainer() {
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            container.setAttribute('role', 'alert');
            container.setAttribute('aria-live', 'polite');
            document.body.appendChild(container);
        }
        return container;
    }

    function create(message, options = {}) {
        const {
            type = 'info',
            title = null,
            duration = 4000,
            closable = true
        } = options;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const iconHtml = icons[type] || icons.info;

        toast.innerHTML = `
            <span class="toast-icon">${iconHtml}</span>
            <div class="toast-content">
                ${title ? `<p class="toast-title">${escapeHtml(title)}</p>` : ''}
                <p class="toast-message">${escapeHtml(message)}</p>
            </div>
            ${closable ? `<button class="toast-close" aria-label="Close notification">&times;</button>` : ''}
        `;

        const closeBtn = toast.querySelector('.toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => dismiss(toast));
        }

        getContainer().appendChild(toast);

        // Auto-dismiss after duration
        if (duration > 0) {
            setTimeout(() => dismiss(toast), duration);
        }

        return toast;
    }

    function dismiss(toast) {
        if (!toast || toast.classList.contains('removing')) return;

        toast.classList.add('removing');
        toast.addEventListener('animationend', () => {
            toast.remove();
        }, { once: true });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public API
    return {
        show: create,
        success: (msg, opts = {}) => create(msg, { ...opts, type: 'success' }),
        error: (msg, opts = {}) => create(msg, { ...opts, type: 'error' }),
        warning: (msg, opts = {}) => create(msg, { ...opts, type: 'warning' }),
        info: (msg, opts = {}) => create(msg, { ...opts, type: 'info' }),
        dismiss
    };
})();

// Expose globally
window.Toast = Toast;

// Convenience functions
window.showToast = Toast.show;
window.showSuccess = Toast.success;
window.showError = Toast.error;
window.showWarning = Toast.warning;
window.showInfo = Toast.info;
