# EasyRFP Design System

A comprehensive design system for building a sleek, intuitive SaaS experience.

---

## Quick Start

### CSS Architecture

```html
<!-- Load in this order in your HTML -->
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/components.css">
<link rel="stylesheet" href="/static/css/layout.css">
<link rel="stylesheet" href="/static/css/utilities.css">

<!-- Page-specific styles -->
<link rel="stylesheet" href="/static/css/pages/opportunities.css">

<!-- JavaScript -->
<script src="/static/js/toast.js"></script>
```

---

## 1. Color System

### Primary Brand Color
The primary action color is **Blue (#2563eb)** - consistent throughout the app.

```css
--color-primary: #2563eb;
--color-primary-hover: #1d4ed8;
--color-primary-light: #dbeafe;
--color-primary-dark: #1e40af;
```

### Status Colors
```css
--color-success: #10b981;  /* Green - confirmations, completed */
--color-warning: #f59e0b;  /* Amber - caution, attention */
--color-danger: #ef4444;   /* Red - errors, destructive */
--color-info: #0ea5e9;     /* Blue - informational */
```

### Semantic Colors
```css
--bg-page: #f8fafc;        /* Page background */
--bg-card: #ffffff;        /* Card/modal background */
--bg-muted: #f1f5f9;       /* Muted sections */
--border-default: #e2e8f0; /* Standard borders */
--text-main: #0f172a;      /* Primary text */
--text-dim: #64748b;       /* Secondary text */
```

---

## 2. Button System

### Button Variants

```html
<!-- Primary - Main actions -->
<button class="btn-primary">Save Changes</button>

<!-- Secondary - Alternative actions -->
<button class="btn-secondary">Cancel</button>

<!-- Ghost - Outline style -->
<button class="btn-ghost">Learn More</button>

<!-- Danger - Destructive actions -->
<button class="btn-danger">Delete</button>

<!-- Success - Positive actions -->
<button class="btn-success">Approve</button>
```

### Button Sizes

```html
<button class="btn-primary btn-sm">Small</button>
<button class="btn-primary">Default</button>
<button class="btn-primary btn-lg">Large</button>
```

### Button States

```html
<!-- Disabled -->
<button class="btn-primary" disabled>Disabled</button>

<!-- Loading -->
<button class="btn-primary loading">Saving...</button>
```

---

## 3. Form Components

### Basic Form Group

```html
<div class="form-group">
    <label class="form-label required">Email Address</label>
    <input type="email" class="form-input" placeholder="you@company.com">
    <span class="form-hint">We'll never share your email.</span>
</div>
```

### Form with Error State

```html
<div class="form-group error">
    <label class="form-label">Password</label>
    <input type="password" class="form-input">
    <span class="form-error">Password must be at least 8 characters.</span>
</div>
```

### Checkbox & Radio

```html
<label class="form-checkbox">
    <input type="checkbox">
    <span>I agree to the terms</span>
</label>

<label class="form-radio">
    <input type="radio" name="plan" value="starter">
    <span>Starter Plan</span>
</label>
```

---

## 4. Toast Notifications

### JavaScript API

```javascript
// Success toast
Toast.success('Bid tracked successfully!');

// Error toast
Toast.error('Failed to save changes');

// Warning toast
Toast.warning('Your session will expire soon');

// Info toast
Toast.info('3 new opportunities available');

// With title
Toast.success('Changes saved', {
    title: 'Success',
    duration: 5000
});
```

### Toast Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `type` | string | 'info' | 'success', 'error', 'warning', 'info' |
| `title` | string | null | Optional title above message |
| `duration` | number | 4000 | Auto-dismiss time in ms (0 = never) |
| `closable` | boolean | true | Show close button |

---

## 5. Card Component

```html
<div class="card">
    <div class="card-header">
        <h2 class="card-title">Recent Opportunities</h2>
        <button class="btn-sm btn-secondary">View All</button>
    </div>
    <p class="card-subtitle">Showing 10 of 156 open bids</p>

    <!-- Card content here -->
</div>
```

---

## 6. Pills & Badges

### Standard Pill
```html
<span class="pill">Professional</span>
```

### Status Pills
```html
<span class="pill pill-success">Active</span>
<span class="pill pill-warning">Pending</span>
<span class="pill pill-danger">Expired</span>
```

---

## 7. Spacing Scale

Use consistent spacing throughout:

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | 4px | Tight spacing |
| `--space-sm` | 8px | Related elements |
| `--space-md` | 16px | Standard spacing |
| `--space-lg` | 24px | Section spacing |
| `--space-xl` | 32px | Large gaps |
| `--space-2xl` | 48px | Page sections |

---

## 8. Typography

### Font Stack
```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
```

### Type Scale
| Token | Size | Usage |
|-------|------|-------|
| `--text-xs` | 11px | Captions, meta |
| `--text-sm` | 13px | Secondary text |
| `--text-base` | 14px | Body text |
| `--text-lg` | 16px | Emphasized text |
| `--text-xl` | 18px | Subheadings |
| `--text-2xl` | 22px | Section titles |
| `--text-3xl` | 28px | Page titles |

---

## 9. Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 6px | Small buttons, inputs |
| `--radius-md` | 8px | Standard buttons |
| `--radius-lg` | 12px | Cards |
| `--radius-xl` | 16px | Modals |
| `--radius-pill` | 999px | Pills, avatars |

---

## 10. Shadows

| Token | Usage |
|-------|-------|
| `--shadow-xs` | Subtle depth |
| `--shadow-sm` | Buttons, inputs |
| `--shadow-md` | Hover states |
| `--shadow-lg` | Dropdowns |
| `--shadow-xl` | Modals |
| `--shadow-card` | Card components |

---

## 11. Dark Mode

Dark mode is opt-in via the `data-theme` attribute:

```html
<html data-theme="dark">
```

### Toggle Dark Mode

```javascript
function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

// Load saved preference
const saved = localStorage.getItem('theme');
if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
}
```

---

## 12. Loading States

### Skeleton Loader

```html
<div class="skeleton skeleton-text"></div>
<div class="skeleton skeleton-text short"></div>
<div class="skeleton skeleton-circle"></div>
```

### Button Loading

```html
<button class="btn-primary loading">Saving...</button>
```

---

## 13. Empty States

```html
<div class="empty-state">
    <div class="icon">📭</div>
    <h3>No opportunities yet</h3>
    <p>Start by setting up your preferences to see relevant bids.</p>
    <div class="actions">
        <a href="/preferences" class="btn-primary">Set Preferences</a>
    </div>
</div>
```

---

## 14. Responsive Breakpoints

```css
/* Mobile first */
@media (min-width: 640px)  { /* sm */ }
@media (min-width: 768px)  { /* md */ }
@media (min-width: 1024px) { /* lg */ }
@media (min-width: 1280px) { /* xl */ }
```

---

## 15. Z-Index Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--z-dropdown` | 100 | Dropdowns, tooltips |
| `--z-sticky` | 200 | Sticky headers |
| `--z-overlay` | 300 | Modal overlays |
| `--z-modal` | 400 | Modal dialogs |
| `--z-toast` | 500 | Toast notifications |

---

## 16. Migration Guide

### Replacing Old Color Variables

| Old Variable | New Variable |
|--------------|--------------|
| `--accent-bg` | `--color-primary` |
| `--accent-bg-hover` | `--color-primary-hover` |
| `--accent-text` | `--color-primary` |
| `#4f46e5` (purple) | `#2563eb` (blue) |

### Replacing Inline Styles

Before:
```python
"style='background:#2563eb;color:#fff;padding:6px 10px;border-radius:6px;'"
```

After:
```python
"class='btn-primary btn-sm'"
```

---

## 17. Accessibility

### Focus States
All interactive elements have visible focus states:
```css
:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
}
```

### ARIA Attributes
```html
<!-- Toast container -->
<div class="toast-container" role="alert" aria-live="polite">

<!-- Loading button -->
<button class="btn-primary loading" aria-busy="true">Saving...</button>

<!-- Required field -->
<label class="form-label required" aria-required="true">Email</label>
```

---

## 18. Design Principles

1. **Consistency** - Use design tokens everywhere, never hardcode values
2. **Clarity** - Clear visual hierarchy with proper spacing
3. **Feedback** - Every action has visual feedback (loading, success, error)
4. **Accessibility** - WCAG 2.1 AA compliant focus states and contrast
5. **Performance** - Minimal CSS, no unused styles

---

## File Structure

```
app/web/static/
├── css/
│   ├── tokens.css        # Design tokens (colors, spacing, etc.)
│   ├── components.css    # Reusable components
│   ├── layout.css        # App shell, sidebar, topbar
│   ├── utilities.css     # Helper classes
│   └── pages/
│       ├── opportunities.css
│       └── dashboard.css
├── js/
│   └── toast.js          # Toast notification system
└── images/
    └── ...
```
