console.log("vendor.js loaded");

// === Vendor Guide Drawer logic ===
async function openVendorGuide(slug, ctx) {
  const drawer = document.getElementById("guide-drawer");
  const overlay = document.getElementById("guide-overlay");
  const title = document.getElementById("guide-title");
  const agency = document.getElementById("guide-agency");
  const content = document.getElementById("guide-content");

  title.textContent = "How to bid";
  agency.textContent = slug.replaceAll("-", " ");
  content.innerHTML = "Loading…";

  overlay.style.display = "block";
  drawer.setAttribute("aria-hidden", "false");

  async function fetchGuide() {
    const r = await fetch(`/vendor-guides/${slug}`, { credentials: "include" });
    if (r.ok) return r.text();
    if (r.status === 404 && slug === "city-of-columbus") {
      // force build then retry once
      const rf = await fetch(`/vendor-guides/city-of-columbus/refresh`, { credentials: "include" });
      if (rf.ok) {
        const r2 = await fetch(`/vendor-guides/${slug}`, { credentials: "include" });
        if (r2.ok) return r2.text();
      }
    }
    throw new Error(`Guide fetch failed (${r.status})`);
  }

  try {
    const html = await fetchGuide();
    content.innerHTML = html;
  } catch (e) {
    // Graceful client-side fallback guide
    const agencyName = (ctx && (ctx.agency_name || ctx.agency || "")) || slug.replaceAll("-"," ");
    const src = (ctx && ctx.source_url) ? `<a href="${ctx.source_url}" target="_blank" rel="noreferrer">Open the official posting</a>` : "";
    content.innerHTML = `
      <article style="font-size:13px; line-height:1.55; color:#0f172a;">
        <h2 style="font-size:15px; margin:0 0 6px 0;">${agencyName} — How to Bid</h2>
        <div class="muted" style="font-size:11px; margin-bottom:10px;">This is a quick-start guide. Official instructions may vary. ${src}</div>
        <ol style="margin:0 0 10px 18px;">
          <li style="margin-bottom:6px;">Register as a vendor on the agency’s portal (if required).</li>
          <li style="margin-bottom:6px;">Download the solicitation package and all attachments.</li>
          <li style="margin-bottom:6px;">Note the due date and submit method (online upload vs. sealed bid).</li>
          <li style="margin-bottom:6px;">Prepare required documents (bid form, pricing sheet, W‑9, certifications, insurance, bonds if needed).</li>
          <li style="margin-bottom:6px;">Follow the submission instructions exactly; late bids are not accepted.</li>
          <li style="margin-bottom:6px;">If you have questions, use the portal’s Q&A contact by the posted deadline.</li>
        </ol>
        <div class="muted" style="font-size:12px;">Tip: Save files here and track progress from your dashboard.</div>
      </article>`;
  }
}

// Close helper (called from the X button)
const TrackerGuide = {
  close() {
    document.getElementById("guide-overlay").style.display = "none";
    document.getElementById("guide-drawer").setAttribute("aria-hidden", "true");
  },
};
