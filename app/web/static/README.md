Static asset layout
-------------------

- css/: Stylesheets (global and page-scoped)
  - base.css: Global primitives (typography, layout, buttons)
  - pages.css: Shared page-level blocks (plans, account, team, onboarding, etc.)
  - dashboard.css, opportunities.css, bid_tracker.css, vendor.css, highlight.css: Page/feature-specific styles
- js/: JavaScript bundles
  - tracker_dashboard.js, rfq_modal.js, bid_tracker.js, vendor.js, highlight.js
  - utils.js (shared helpers; add here as needed)
- img/: Images and icons (SVG preferred; PNG fallback)
  - Consider subfolders (e.g., img/nav/, img/brand/) as you add assets.

Conventions:
- Use kebab-case filenames.
- Prefer SVGs for icons/logos; include PNG only when necessary.
- Keep page-specific assets scoped; load only where needed.
