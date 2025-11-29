import uuid
from datetime import datetime
from urllib.parse import quote_plus

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from sqlalchemy import text

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.core.calendar_token import parse_calendar_token, make_calendar_token
from app.core.settings import settings
from app.api._layout import page_shell
from app.core.cache_bust import versioned_static

router = APIRouter(tags=["calendar"])

APP_BASE_URL = getattr(settings, "PUBLIC_APP_URL", "http://localhost:8000")


def _ical_escape(val: str) -> str:
    return (
        val.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _build_ics(email: str, rows: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EasyRFP//Calendar//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:EasyRFP Due Dates ({email})",
    ]
    for r in rows:
        due = r.get("due_date")
        if not due:
            continue
        try:
            due_date = due.date() if hasattr(due, "date") else datetime.fromisoformat(str(due)).date()
        except Exception:
            continue
        uid = f"{r.get('id')}-{email}"
        title = r.get("title") or "Opportunity due"
        agency = r.get("agency_name") or ""
        ext = r.get("external_id") or r.get("id")
        detail_url = f"{APP_BASE_URL}/opportunities?ext={quote_plus(str(ext))}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ical_escape(uid)}",
                f"SUMMARY:{_ical_escape(title)}",
                f"DESCRIPTION:{_ical_escape(f'{agency} — Due soon. View: {detail_url}')}",
                f"DTSTART;VALUE=DATE:{due_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(due_date).strftime('%Y%m%d')}",
                f"URL:{_ical_escape(detail_url)}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


@router.get("/calendar.ics", response_class=PlainTextResponse)
async def calendar_feed(request: Request, token: str | None = None):
    """
    iCal feed of tracked opportunities' due dates.
    Accepts a signed token (?token=...) or falls back to the current session user.
    """
    email = parse_calendar_token(token)
    if not email:
        email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT o.id, o.title, o.agency_name, o.due_date, o.external_id
            FROM user_bid_trackers t
            JOIN users u ON u.id = t.user_id
            JOIN opportunities o ON o.id = t.opportunity_id
            WHERE lower(u.email) = lower(:email)
              AND o.due_date IS NOT NULL
              AND o.status = 'open'
            ORDER BY o.due_date ASC
            """,
            {"email": email},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    ics = _build_ics(email, rows)
    headers = {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Disposition": 'attachment; filename="easyrfp-calendar.ics"',
    }
    return PlainTextResponse(ics, media_type="text/calendar", headers=headers)


@router.get("/api/calendar/token", response_class=PlainTextResponse)
async def issue_calendar_token(request: Request):
    """
    Return a signed calendar token for the current user.
    """
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return PlainTextResponse(make_calendar_token(email))


# Cache busting is now handled automatically by versioned_static()


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """
    Marketing-style calendar page (replica of Homepage_test/calendar.html) rendered in the app shell.
    """
    user_email = get_current_user_email(request)
    body = f"""
<link rel="stylesheet" href="{versioned_static('css/dashboard.css')}">
<link rel="stylesheet" href="{versioned_static('css/calendar.css')}">
<main class="page calendar-page">
  <div class="calendar-header fade-in">
    <div class="calendar-title-section">
      <h1 class="calendar-title">Calendar</h1>
      <p class="calendar-subtitle">Track all your bid deadlines and important dates</p>
    </div>
    <div class="calendar-actions">
      <button class="calendar-view-btn active">Month</button>
      <button class="calendar-view-btn">Week</button>
      <button class="calendar-view-btn">List</button>
    </div>
  </div>

  <div class="calendar-nav fade-in stagger-1">
    <button class="nav-arrow" id="prevMonth">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M15 18l-6-6 6-6"/>
      </svg>
    </button>
    <h2 class="current-month" id="currentMonth">December 2025</h2>
    <button class="nav-arrow" id="nextMonth">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 18l6-6-6-6"/>
      </svg>
    </button>
    <button class="today-btn" id="todayBtn">Today</button>
  </div>

  <div class="calendar-container fade-in stagger-2">
    <div class="calendar-grid">
      <div class="calendar-weekdays">
        <div class="weekday">Sun</div>
        <div class="weekday">Mon</div>
        <div class="weekday">Tue</div>
        <div class="weekday">Wed</div>
        <div class="weekday">Thu</div>
        <div class="weekday">Fri</div>
        <div class="weekday">Sat</div>
      </div>
      <div class="calendar-days" id="calendarDays">
      </div>
    </div>

    <div class="calendar-sidebar">
      <div class="sidebar-section">
        <h3 class="sidebar-title">Upcoming Deadlines</h3>
        <div class="upcoming-list" id="upcomingList">
        </div>
      </div>

      <div class="sidebar-section">
        <h3 class="sidebar-title">Legend</h3>
        <div class="legend-list">
          <div class="legend-item">
            <span class="legend-dot urgent"></span>
            <span>Urgent (Due Today)</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot due-soon"></span>
            <span>Due Soon (3 days)</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot active"></span>
            <span>Active Bids</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot meeting"></span>
            <span>Meetings</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</main>

<script>
document.addEventListener('DOMContentLoaded', function() {
  const events = [
    { date: '2025-12-02', title: 'Safety Boots Supply Contract', type: 'urgent', agency: 'City of Columbus' },
    { date: '2025-12-03', title: 'Yard Waste Processing RFP', type: 'due-soon', agency: 'Franklin County' },
    { date: '2025-12-05', title: 'HVAC Services Contract', type: 'active', agency: 'COTA' },
    { date: '2025-12-08', title: 'Pre-bid Conference Call', type: 'meeting', agency: 'Ohio DOT' },
    { date: '2025-12-10', title: 'Fleet Management System', type: 'active', agency: 'City of Dublin' },
    { date: '2025-12-12', title: 'IT Infrastructure Upgrade', type: 'due-soon', agency: 'Franklin County' },
    { date: '2025-12-15', title: 'Snow Removal Services', type: 'active', agency: 'City of Westerville' },
    { date: '2025-12-18', title: 'Quarterly Review Meeting', type: 'meeting', agency: 'Internal' },
    { date: '2025-12-20', title: 'Janitorial Services RFP', type: 'active', agency: 'Columbus City Schools' },
    { date: '2025-12-22', title: 'Emergency Vehicle Maintenance', type: 'urgent', agency: 'Franklin County' },
    { date: '2025-12-28', title: 'Office Supplies Contract', type: 'active', agency: 'State of Ohio' },
    { date: '2025-11-26', title: 'Landscape Maintenance', type: 'urgent', agency: 'City of Columbus' },
    { date: '2025-11-28', title: 'Building Security Audit', type: 'due-soon', agency: 'COTA' },
    { date: '2025-11-29', title: 'Team Strategy Meeting', type: 'meeting', agency: 'Internal' },
  ];

  let currentDate = new Date();
  let currentMonth = currentDate.getMonth();
  let currentYear = currentDate.getFullYear();

  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'];

  function renderCalendar() {
    const calendarDays = document.getElementById('calendarDays');
    const currentMonthEl = document.getElementById('currentMonth');
    
    currentMonthEl.textContent = `${monthNames[currentMonth]} ${currentYear}`;
    
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const startingDay = firstDay.getDay();
    const totalDays = lastDay.getDate();
    
    const prevLastDay = new Date(currentYear, currentMonth, 0).getDate();
    
    let html = '';
    
    for (let i = startingDay - 1; i >= 0; i--) {
      html += `<div class="calendar-day other-month">${prevLastDay - i}</div>`;
    }
    
    const today = new Date();
    for (let day = 1; day <= totalDays; day++) {
      const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayEvents = events.filter(e => e.date === dateStr);
      
      const isToday = day === today.getDate() && 
                      currentMonth === today.getMonth() && 
                      currentYear === today.getFullYear();
      
      let dayClass = 'calendar-day';
      if (isToday) dayClass += ' today';
      if (dayEvents.length > 0) dayClass += ' has-events';
      
      let eventsHtml = '';
      dayEvents.slice(0, 3).forEach(event => {
        eventsHtml += `<div class="day-event ${event.type}">${event.title}</div>`;
      });
      if (dayEvents.length > 3) {
        eventsHtml += `<div class="day-event more">+${dayEvents.length - 3} more</div>`;
      }
      
      html += `
        <div class="${dayClass}" data-date="${dateStr}">
          <span class="day-number">${day}</span>
          <div class="day-events">${eventsHtml}</div>
        </div>
      `;
    }
    
    const remainingDays = 42 - (startingDay + totalDays);
    for (let i = 1; i <= remainingDays; i++) {
      html += `<div class="calendar-day other-month">${i}</div>`;
    }
    
    calendarDays.innerHTML = html;
    renderUpcoming();
  }

  function renderUpcoming() {
    const upcomingList = document.getElementById('upcomingList');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const upcoming = events
      .filter(e => new Date(e.date) >= today)
      .sort((a, b) => new Date(a.date) - new Date(b.date))
      .slice(0, 5);
    
    let html = '';
    upcoming.forEach(event => {
      const eventDate = new Date(event.date);
      const diffDays = Math.ceil((eventDate - today) / (1000 * 60 * 60 * 24));
      let dateLabel;
      if (diffDays === 0) dateLabel = 'Today';
      else if (diffDays === 1) dateLabel = 'Tomorrow';
      else dateLabel = eventDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      
      html += `
        <div class="upcoming-item ${event.type}">
          <div class="upcoming-dot"></div>
          <div class="upcoming-content">
            <div class="upcoming-title">${event.title}</div>
            <div class="upcoming-meta">
              <span>${event.agency}</span>
              <span class="upcoming-date">${dateLabel}</span>
            </div>
          </div>
        </div>
      `;
    });
    
    upcomingList.innerHTML = html;
  }

  document.getElementById('prevMonth').addEventListener('click', () => {
    currentMonth--;
    if (currentMonth < 0) {
      currentMonth = 11;
      currentYear--;
    }
    renderCalendar();
  });

  document.getElementById('nextMonth').addEventListener('click', () => {
    currentMonth++;
    if (currentMonth > 11) {
      currentMonth = 0;
      currentYear++;
    }
    renderCalendar();
  });

  document.getElementById('todayBtn').addEventListener('click', () => {
    const today = new Date();
    currentMonth = today.getMonth();
    currentYear = today.getFullYear();
    renderCalendar();
  });

  document.querySelectorAll('.calendar-view-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.calendar-view-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
    });
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

  renderCalendar();
});
</script>
    """
    return page_shell(body, "Calendar", user_email)
