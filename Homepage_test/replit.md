# EasyRFP - Government Bid Tracking Platform

## Overview
Modern landing page and dashboard for EasyRFP - a government bid tracking platform for contractors in Central Ohio. Features a sleek, minimal white aesthetic with forest green (#126a45) branding.

## Project Structure
```
.
├── index.html           # Main landing page
├── style.css            # Landing page styling
├── script.js            # Landing page animations
├── dashboard-demo.html  # Premium dashboard demo
├── dashboard.css        # Dashboard styling (showstopper design)
├── calendar.html        # Calendar view page
├── calendar.css         # Calendar-specific styling
├── documents.html       # Documents management page
├── documents.css        # Documents page styling
├── opportunities.html   # Open bids discovery page
├── opportunities.css    # Opportunities page styling
├── account.html         # My Account settings page
├── account.css          # Account page styling
├── settings.html        # App-wide settings page
├── settings.css         # Settings page styling
├── billing.html         # Billing & Plans comparison page
├── billing.css          # Billing page styling
├── notifications.js     # Shared notifications sidebar functionality
└── attached_assets/     # Original reference files
```

## Design System

### Color Palette
- **Primary Brand**: #126a45 (Forest Green) → #22c55e (Light Green)
- **Background**: #ffffff (Pure White)
- **Secondary Background**: #f8fafb (Off White)
- **Card Background**: #f1f5f9 (Light Gray)
- **Accent/Warning**: #f59e0b (Orange)
- **Success**: #10b981 (Emerald)
- **Danger**: #ef4444 (Red)
- **Info**: #3b82f6 (Blue)
- **Text Primary**: #0f172a (Dark)
- **Text Secondary**: #475569 (Medium)
- **Text Tertiary**: #94a3b8 (Light)

### Design Philosophy
- **Minimal & Clean**: White background, subtle shadows, generous whitespace
- **Professional**: Suited for government contractors and enterprise teams
- **Modern SaaS**: Inspired by Linear, Stripe, Vercel, Notion
- **Bold Typography**: Large headlines, clear hierarchy, Inter font
- **Premium Interactions**: Smooth transitions, micro-animations, hover effects

## Dashboard Features (Showstopper Design)

### Hero Stats Section
- 4 animated stat cards with gradient featured card
- Counter animations that count up on load
- Hover effects with glow and lift

### Team Bar
- Stacked team avatars with hover animations
- Team info display
- Shared dashboard action button

### Upcoming Deadlines Timeline
- Visual timeline with connected dots
- Color-coded past/upcoming items
- Hover animations with slide effect

### Solicitation Cards
- Expandable cards with click-to-reveal details
- Progress rings showing completion percentage
- Status indicators (urgent, due soon, active)
- Checklist progress tracking
- File attachments display
- Quick action buttons

### Bid Status Chart
- Donut chart with animated segments
- Interactive legend
- Center statistics

### Activity Feed
- Recent team activity with icons
- Timestamp display
- Hover animations

## Calendar Features

### Monthly Grid
- Full month view with day cells
- Previous/next month navigation
- "Today" button for quick navigation
- Week/Month/List view toggles (Month active)

### Event Display
- Events shown on calendar days with status colors
- Color-coded by type: urgent (red), due-soon (orange), active (green), meeting (blue)
- "+N more" indicator when day has many events
- Today's date highlighted

### Upcoming Deadlines Sidebar
- Next 5 upcoming events sorted by date
- Relative date labels (Today, Tomorrow, or date)
- Status-colored dots with pulse animation for urgent items

### Legend
- Visual guide for event type colors
- Helps users understand status at a glance

## Documents Features

### Folder Organization
- 5 folder categories: Active Bids, Proposals, Templates, Contracts, Archive
- Folder cards with file counts
- Hover effects with lift and glow

### File Cards
- Grid and list view options
- File type indicators with color coding:
  - PDF (red), DOCX (blue), XLSX (green), PPTX (orange)
- File metadata (size, modified date)
- Hover actions (download, more options)

### Search & Filters
- Real-time search by filename
- Category filters (All, Proposals, Templates, Contracts)
- View toggle (grid/list)

### Actions
- Upload button (primary green)
- New Folder button (secondary outline)

### Micro-interactions
- Fade-in animations on scroll
- Staggered element reveals
- Smooth CSS transitions (150-350ms)
- Button hover states with scale/lift
- Card hover with glow effects

## Opportunities Features

### Stats Section
- 4 animated stat cards (Open Bids, Agencies, Next Due Date, Tracking)
- Counter animations on page load
- Featured gradient card for tracking count

### Filter Panel
- Agency dropdown filter
- Search by title input
- Specialties dropdown
- Due date range filter
- Open only toggle switch
- Sort by options (Soonest due, Recently added, Title A-Z)
- Apply/Reset filter buttons

### Data Table
- Solicitation ID with monospace styling
- Title with category meta tag
- Agency name (truncated if long)
- Date added and due date columns
- Color-coded due dates (urgent = red)
- Status badges (Open/Closed)
- Action buttons: View Source, Track bid
- Staggered row animations

### Pagination
- Results count display
- Page number buttons with active state
- Previous/Next navigation

## Technology Stack
- Pure HTML5, CSS3, vanilla JavaScript
- No framework dependencies
- Google Fonts (Inter)
- CSS custom properties for theming
- IntersectionObserver for scroll animations
- requestAnimationFrame for smooth counters

## Target Audience
- Government contractors
- Capture teams
- Municipal bid managers
- Central Ohio businesses

## Recent Changes
- 2025-11-24: Initial landing page with dark navy design
- 2025-11-24: Redesigned with warm orange/teal palette
- 2025-11-24: Transformed to minimal white theme
- 2025-11-24: Updated brand color to forest green (#126a45)
- 2025-11-25: Created premium "showstopper" dashboard with:
  - Animated counter stats
  - Interactive timeline
  - Expandable solicitation cards with progress rings
  - Donut chart visualization
  - Activity feed
  - Premium micro-interactions and transitions
- 2025-11-26: Added Calendar page with:
  - Monthly calendar grid with navigation
  - Bid deadlines displayed on calendar days
  - Color-coded events (urgent, due-soon, active, meeting)
  - Upcoming Deadlines sidebar
  - Legend for event types
  - Same look and feel as dashboard
- 2025-11-27: Added Documents page with:
  - Folder organization (Active Bids, Proposals, Templates, Contracts, Archive)
  - File cards with type indicators (PDF, DOCX, XLSX, PPTX)
  - Search and filter functionality
  - Grid/List view toggle
  - Upload and New Folder buttons
  - Hover effects and micro-interactions
- 2025-11-27: Added Opportunities page with:
  - Animated stats row (Open Bids, Agencies, Next Due, Tracking)
  - Comprehensive filter panel with search, dropdowns, toggle
  - Clean data table with solicitations
  - Staggered row animations and hover effects
  - Track/untrack bid functionality
  - Pagination controls
- 2025-12-01: Added comprehensive Settings page with:
  - 6 organized sections via left nav (Display, Notifications, Default Views, Data & Privacy, Integrations, Workspace)
  - Display & Appearance: Theme selector (Light/Dark/System), sidebar state, compact mode toggle, date/time format, timezone
  - Notifications & Alerts: Bid deadline reminders with multiple timing options, email digest frequency, browser notifications, quiet hours with time range
  - Default Views: Calendar view toggle, documents view/sort options, opportunities sort, items per page, saved filter presets
  - Data & Privacy: Usage analytics toggle, activity log visibility, cookie preferences, data export (CSV/PDF/Excel/JSON), data retention, clear cache
  - Integrations: Connected apps grid (Google, Slack, Teams, Salesforce, Dropbox, Zapier), API key management, webhooks configuration
  - Workspace Settings: Workspace name/logo, default member role, invite restrictions, custom bid categories, approval workflows, SSO/SAML, audit log
  - Save/Reset actions with toast notification
  - Responsive design with mobile-friendly layouts
- 2025-11-30: Added premium My Account page with:
  - Large profile header with avatar, badges, and actions
  - 6 organized tabs (Overview, Profile, Billing, Team, Notifications, Security)
  - Beautiful gradient plan card showing subscription details
  - Usage statistics with animated progress bars
  - Quick actions grid with colorful icons
  - Recent activity feed
  - Team preview with online status indicators
  - Connected apps/integrations section
  - Profile & organization forms with validation
  - Billing history table with download buttons
  - Payment method management with add/edit
  - Team member cards with role badges
  - Pending invitations management
  - Email & push notification toggles
  - Password change with strength indicator
  - Two-factor authentication setup
  - Active sessions management
  - Danger zone with data export and account deletion
- 2025-12-02: Added notifications sidebar across all dashboard pages:
  - Slide-out drawer (360px wide) triggered by bell icon
  - Notification categories with tabs (All, Unread, Deadlines, Team)
  - Color-coded notification items (urgent, warning, success, team)
  - Mark all as read functionality
  - Individual dismiss buttons
  - Date grouping (Today, Yesterday)
  - Link to notification settings
  - Shared notifications.js for consistent behavior
  - Smooth open/close animations with overlay
- 2025-12-02: Comprehensive landing page overhaul:
  - Updated hero messaging: "Win more bids. Spend less time searching."
  - Added hero metrics row (142 opportunities, 21 portals, 24/7 alerts, 5min speed)
  - Added interactive app preview mockup showing dashboard experience
  - Enhanced trust section with key stats ($12M+ contracts won, 150+ teams, 21 portals)
  - Added municipal badges with icons for local agencies (Columbus, COTA, Franklin County, etc.)
  - Redesigned features section with 4 feature cards (Monitoring, Calendar, Documents, Team)
  - Added product showcase with visual mockups (Opportunities, Calendar, Documents)
  - Added workflow steps section (3-step process)
  - Added pricing section with 3 tiers (Starter free, Professional $49/mo, Team $149/mo)
  - Added testimonials section with 3 customer testimonials and stats
  - Enhanced footer with organized links grid
  - Restored Resources, Help nav links and language selector
- 2025-12-02: Added Billing & Plans page with:
  - Clean 4-column plan comparison grid (Free, Professional, Team, Enterprise)
  - Current plan highlighting with badge
  - "Most Popular" badge on Team plan
  - Feature lists for each tier
  - Feature comparison table
  - FAQ section
  - Linked from Account page "Compare Plans" button

## Running the Project
```bash
python -m http.server 5000
```

## URLs
- Landing Page: `/` or `/index.html`
- Dashboard Demo: `/dashboard-demo.html`
- Calendar View: `/calendar.html`
- Documents: `/documents.html`
- Opportunities: `/opportunities.html`
- My Account: `/account.html`
- Settings: `/settings.html`
- Billing & Plans: `/billing.html`

## User Preferences
- Sleek minimal vibe - white background, clean design
- Not a copycat - inspired by but distinct from competitors
- Modern SaaS aesthetic - Linear, Stripe, Notion, Vercel style
- Bold and confident - entrepreneurial voice, not corporate
- Forest green brand identity (#126a45) - professional, trustworthy
- "Showstopper" dashboard design - premium feel, impressive to clients
