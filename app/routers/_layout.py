# app/routers/_layout.py

from typing import Optional

def _nav_links_html(user_email: Optional[str]) -> str:
    if user_email:
        return """
        <a href="/">Overview</a>
        <a href="/opportunities">Open Opportunities</a>
        <a href="/onboarding">Preferences</a>
        <a href="/account">My Account</a>
        <a href="/logout">Logout</a>
        """
    else:
        return """
        <a href="/">Home</a>
        <a href="/signup">Sign up</a>
        <a href="/login">Sign in</a>
        """


def page_shell(body_html: str, title: str, user_email: Optional[str]) -> str:
    """
    Shared shell for all pages.
    user_email:
      - None if anonymous
      - "someone@company.com" if logged in
    """

    nav_links = _nav_links_html(user_email)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
<style>
    :root {{
        --bg-page: #f9fafb;
        --bg-card: #ffffff;
        --border-card: #e5e7eb;
        --text-main: #111827;
        --text-dim: #6b7280;
        --accent-bg: #4f46e5;
        --accent-bg-hover: #4338ca;
        --accent-text: #4f46e5;
        --pill-bg: #eef2ff;
        --pill-border: #c7d2fe;
        --pill-text: #4f46e5;
        --radius-card: 16px;
        --radius-pill: 999px;
        --shadow-card: 0 20px 40px rgba(0,0,0,0.06);
    }}

    * {{
        box-sizing: border-box;
    }}

    body {{
        margin: 0;
        background: var(--bg-page);
        color: var(--text-main);
        font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
        line-height: 1.45;
        -webkit-font-smoothing: antialiased;
        padding: 0 16px 48px;
    }}

    header.navbar {{
        max-width: 1100px;
        margin: 0 auto;
        padding: 20px 0 12px;
        display: flex;
        flex-wrap: wrap;
        align-items: flex-start;
        justify-content: space-between;
        row-gap: 12px;
        border-bottom: 1px solid #e5e7eb;
    }}

    .brand-block {{
        display:flex;
        flex-direction:column;
    }}

    .brand-name {{
        font-size: 16px;
        font-weight: 600;
        color: var(--text-main);
    }}

    .brand-tagline {{
        font-size: 12px;
        color: var(--text-dim);
    }}

    nav.navlinks {{
        display:flex;
        flex-wrap:wrap;
        column-gap:16px;
        row-gap:8px;
        font-size:14px;
        font-weight:500;
        align-items:flex-start;
    }}

    nav.navlinks a {{
        color: var(--accent-text);
        text-decoration:none;
    }}

    nav.navlinks a:hover {{
        text-decoration:underline;
    }}

    main.page {{
        max-width: 900px;
        margin: 24px auto 0;
        display: grid;
        row-gap: 24px;
    }}

    .card {{
        background: var(--bg-card);
        border-radius: var(--radius-card);
        border: 1px solid var(--border-card);
        box-shadow: var(--shadow-card);
        padding: 20px 24px;
    }}

    .section-heading {{
        font-size: 20px;
        font-weight:600;
        color: var(--text-main);
        margin:0 0 8px 0;
        line-height:1.2;
        letter-spacing:-0.03em;
    }}

    .subtext {{
        font-size:13px;
        color: var(--text-dim);
        line-height:1.4;
        margin:0 0 16px 0;
    }}

    .flex-grid {{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));
        gap:16px;
    }}

    .mini-head {{
        font-size:14px;
        font-weight:600;
        color: var(--text-main);
        margin:0 0 4px;
    }}

    .mini-desc {{
        font-size:13px;
        color: var(--text-dim);
        line-height:1.4;
        margin:0 0 8px;
    }}

    a.cta-link {{
        font-size:14px;
        font-weight:500;
        text-decoration:underline;
        color: var(--accent-text);
    }}

    a.button-primary {{
        display:inline-block;
        background: var(--accent-bg);
        color:#fff;
        text-decoration:none;
        font-size:14px;
        font-weight:600;
        line-height:1.2;
        padding:10px 14px;
        border-radius:8px;
        border:1px solid rgba(0,0,0,0.05);
    }}

    a.button-primary:hover {{
        background: var(--accent-bg-hover);
    }}

    .table-wrap {{
        overflow-x:auto;
    }}

    table {{
        width:100%;
        border-collapse:collapse;
        font-size:14px;
        line-height:1.4;
    }}

    th {{
        text-align:left;
        padding:8px 6px;
        border-bottom:1px solid #e5e7eb;
        color:#374151;
        font-weight:600;
        font-size:13px;
        white-space:nowrap;
    }}

    td {{
        padding:8px 6px;
        border-bottom:1px solid #f1f5f9;
        vertical-align:top;
        font-size:13px;
        color:var(--text-main);
    }}

    .muted {{
        color: var(--text-dim);
        font-size:12px;
        line-height:1.3;
    }}

    .pill {{
        display:inline-block;
        font-size:12px;
        line-height:1.2;
        background:var(--pill-bg);
        color:var(--pill-text);
        padding:3px 8px;
        border-radius:var(--radius-pill);
        border:1px solid var(--pill-border);
        font-weight:500;
    }}

    .form-row {{
        display:flex;
        flex-wrap:wrap;
        gap:16px;
        margin:0 0 24px;
    }}

    .form-col {{
        flex:1 1 240px;
        min-width:240px;
    }}

    label.label-small {{
        font-size:12px;
        font-weight:500;
        color:#374151;
        margin-bottom:4px;
        display:block;
    }}

    input[type="text"],
    select {{
        width:100%;
        font-size:14px;
        line-height:1.4;
        padding:8px 10px;
        border-radius:8px;
        border:1px solid #d1d5db;
        background:#fff;
        color:#111827;
        outline:none;
    }}

    input[type="text"]:focus,
    select:focus {{
        border-color: var(--accent-bg);
        box-shadow:0 0 0 3px rgba(79,70,229,0.2);
    }}

    button.button-primary {{
        appearance:none;
        border:none;
        background: var(--accent-bg);
        color:#fff;
        border-radius:8px;
        font-size:14px;
        font-weight:600;
        line-height:1.2;
        padding:10px 14px;
        cursor:pointer;
    }}

    button.button-primary:hover {{
        background: var(--accent-bg-hover);
    }}

    .agency-grid {{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));
        gap:8px 16px;
    }}

    .agency-choice {{
        font-size:13px;
        font-weight:500;
        color:#111;
        display:block;
    }}

    .agency-choice input {{
        margin-right:6px;
        accent-color: var(--accent-bg);
    }}

    code.chip {{
        font-size:12px;
        background:#f3f4f6;
        padding:2px 6px;
        border-radius:6px;
        border:1px solid #e5e7eb;
        color:#374151;
    }}

    /* NEW: pagination controls for /opportunities */
    .pagination-bar {{
        display:flex;
        flex-wrap:wrap;
        gap:8px;
        align-items:center;
        justify-content:flex-start;
        margin-top:16px;
        font-size:13px;
    }}

    .page-link {{
        display:inline-block;
        padding:6px 10px;
        border-radius:8px;
        border:1px solid #d1d5db;
        background:#fff;
        font-weight:500;
        line-height:1.2;
        text-decoration:none;
        color:#374151;
    }}

    .page-link:hover {{
        text-decoration:none;
        border-color: var(--accent-bg);
        color: var(--accent-bg);
    }}

    .page-link.current {{
        background: var(--accent-bg);
        border-color: var(--accent-bg);
        color:#fff;
    }}

    .page-link.disabled {{
        opacity:0.4;
        pointer-events:none;
        cursor:default;
    }}

    .reveal {{
        opacity: 0;
        transform: translateY(16px);
        transition: opacity 0.5s ease, transform 0.5s ease;
    }}

    .reveal.reveal-visible {{
        opacity: 1;
        transform: translateY(0);
    }}

</style>
</head>
<body>

<header class="navbar">
    <div class="brand-block">
        <div class="brand-name">Muni Alerts</div>
        <div class="brand-tagline">Stop missing public bids.</div>
    </div>
    <nav class="navlinks">
        {nav_links}
    </nav>
</header>

<main class="page">
{body_html}
</main>

<script>
document.addEventListener("DOMContentLoaded", function () {{
    const revealEls = Array.prototype.slice.call(document.querySelectorAll(".reveal"));

    if ("IntersectionObserver" in window) {{
        const obs = new IntersectionObserver((entries) => {{
            entries.forEach((entry) => {{
                if (entry.isIntersecting) {{
                    entry.target.classList.add("reveal-visible");
                    obs.unobserve(entry.target);
                }}
            }});
        }}, {{
            threshold: 0.15
        }});

        revealEls.forEach((el) => obs.observe(el));
    }} else {{
        revealEls.forEach((el) => el.classList.add("reveal-visible"));
    }}
}});
</script>


</body>
</html>

    """
