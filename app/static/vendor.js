console.log("vendor.js loaded");

// === Vendor Guide Drawer logic ===
async function openVendorGuide(slug) {
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
    content.innerHTML = `
      <div class="muted">No guide yet for this agency.</div>
      <div style="margin-top:8px;">
        <button class="btn" id="vg-refresh">Try building it now</button>
      </div>`;
    document.getElementById("vg-refresh")?.addEventListener("click", async () => {
      content.textContent = "Building…";
      try {
        await fetch(`/vendor-guides/city-of-columbus/refresh`, { credentials: "include" });
        const html = await (await fetch(`/vendor-guides/${slug}`, { credentials: "include" })).text();
        content.innerHTML = html;
      } catch {
        content.innerHTML = `<div class="muted">Still not available. Try again later.</div>`;
      }
    });
  }
}

// Close helper (called from the X button)
const TrackerGuide = {
  close() {
    document.getElementById("guide-overlay").style.display = "none";
    document.getElementById("guide-drawer").setAttribute("aria-hidden", "true");
  },
};
