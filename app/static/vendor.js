console.log("Vendor JS loaded sleek mode");

async function openVendorGuide(slug) {
  console.log("openVendorGuide() called with", slug);
  const panel = document.getElementById("vendor-guide-panel");
  const content = document.getElementById("vendor-guide-content");
  const agencyEl = document.getElementById("vendor-guide-agency");
  const overlay = document.getElementById("vendor-overlay");

  document.body.classList.add("sidebar-open");
  panel.classList.add("visible");
  overlay.classList.add("visible");
  content.innerHTML =
    "<div style='font-size:12px;color:#94a3b8;'>Loading guide...</div>";
  agencyEl.textContent = slug.replace(/-/g, " ");

  try {
    const url = window.location.origin + "/vendor-guides/" + slug;
    const resp = await fetch(url);
    if (!resp.ok) {
      content.innerHTML =
        "<div style='color:#b91c1c;font-size:12px;'>Unable to load guide.</div>";
      return;
    }
    const html = await resp.text();
    content.innerHTML = html
      .replaceAll("<script", "<!--script")
      .replaceAll("</script>", "</script-->");
  } catch (err) {
    console.error("Fetch error", err);
    content.innerHTML =
      "<div style='color:#b91c1c;font-size:12px;'>Error loading guide.</div>";
  }
}

function closeVendorGuide() {
  const panel = document.getElementById("vendor-guide-panel");
  const overlay = document.getElementById("vendor-overlay");
  document.body.classList.remove("sidebar-open");
  panel.classList.remove("visible");
  overlay.classList.remove("visible");
}
