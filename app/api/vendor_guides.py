# app/routers/vendor_guides.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from app.vendor_guides import (
    get_vendor_guide_by_slug,
    upsert_vendor_guide_for_columbus,
)

# optional markdown renderer
try:
    from markdown import markdown as md
except ImportError:
    md = None

router = APIRouter(prefix="/vendor-guides", tags=["vendor-guides"])


@router.get("/city-of-columbus/refresh", response_class=JSONResponse)
async def refresh_columbus():
    data = await upsert_vendor_guide_for_columbus()
    return {"ok": True, "data": data}


@router.get("/{agency_slug}", response_class=HTMLResponse)
async def get_guide(agency_slug: str):
    print(f">>> Vendor guide route hit for {agency_slug}")
    guide = await get_vendor_guide_by_slug(agency_slug)
    if not guide:
        if agency_slug == "city-of-columbus":
            guide = await upsert_vendor_guide_for_columbus()
        else:
            raise HTTPException(status_code=404, detail="Guide not found")
    print(">>> Guide fetched OK, returning HTML")

    summary = guide.get("llm_summary") or ""

    if md:
        rendered = md(summary, extensions=["extra", "sane_lists"])
    else:
        rendered = summary.replace("\n", "<br>")

    html = f"""
    <article style="font-size:13px; line-height:1.55; color:#0f172a;">
        <h2 style="font-size:15px; margin-bottom:4px;">
            {guide['agency_name']} – How to Submit
        </h2>
        <p style="margin-top:0; margin-bottom:10px; font-size:11px; color:#64748b;">
            Source: <a href="{guide['source_url']}" target="_blank" rel="noreferrer">official vendor page</a>
            · last updated {guide['updated_at']}
        </p>
        <div id="vendor-guide-markdown" style="
            border:1px solid #e5e7eb;
            border-radius:10px;
            background:#fff;
            padding:12px 16px;
            max-height:calc(100vh - 160px);
            overflow-y:auto;
        ">
            {rendered}
        </div>
            </article>
    """
    return HTMLResponse(content=html)
