from fastapi import APIRouter
import httpx
import urllib.parse

router = APIRouter(tags=["columbus_detail"])

BASE_URL_HEADERS = "https://columbusvendorservices.powerappsportals.com/_api/cr820_rfqheaders"
BASE_URL_ATTACH  = "https://columbusvendorservices.powerappsportals.com/_api/cr820_rfqattachments"
BASE_URL_ITEMS   = "https://columbusvendorservices.powerappsportals.com/_api/cr820_rfqitems"


def _browsery_headers():
    # Some portals care that we look like a browser and accept JSON.
    return {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        ),
    }


#
# 1. MAIN HEADER LOOKUP
#
def build_header_query_url(rfq_case_id: str) -> str:
    # We ask for just this RFQ (case id like "RFQ031521"), all columns.
    params = {
        "$filter": f"cr820_rfqcaseid eq '{rfq_case_id}'",
        "$select": "*",
    }
    return BASE_URL_HEADERS + "?" + urllib.parse.urlencode(params, safe="$, '")


@router.get("/columbus_detail/{rfq_case_id}")
async def get_rfq_header(rfq_case_id: str):
    """
    Main endpoint used by the modal first.
    Returns header-level info like title, due date, department, ship-to, scope, etc.
    Also returns rfq_header_id (GUID) so the frontend can query attachments/items.
    """
    url = build_header_query_url(rfq_case_id)

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_browsery_headers())

    if resp.status_code != 200:
        return {
            "error": "upstream_failed",
            "status_code": resp.status_code,
            "text": resp.text[:2000],
            "url": url,
        }

    data = resp.json()
    records = data.get("value", [])
    if not records:
        return {
            "error": "not_found_or_empty",
            "url": url,
            "raw": data,
        }

    header = records[0]

    def pick(*keys):
        for k in keys:
            if k in header and header[k]:
                return header[k]
        return ""

    # Prefer formatted (human-readable) due date fields
    due_date = pick(
        "cr820_expirydateandtime@OData.Community.Display.V1.FormattedValue",
        "oa_expirydatetimeest@OData.Community.Display.V1.FormattedValue",
        "cr820_expirydateandtime",
        "oa_expirydatetimeest",
    )

    scope_text = pick(
        "cr820_psnrfqdescription",
        "cr820_psnrfqdescription_t_",
    )

    cleaned = {
        "rfq_id":            pick("cr820_rfqcaseid", "cr820_rfqid"),
        "rfq_header_id":     pick("cr820_rfqheaderid"),  # GUID for child lookups
        "title":             pick("cr820_documenttitle", "cr820_name"),
        "department":        pick("cr820_requestingdepartment", "cr820_deliveryname"),
        "delivery_name":     pick("cr820_deliveryname"),
        "delivery_address":  pick("cr820_deliveryaddress"),
        "due_date":          due_date,
        "status_text":       pick("cr820_statuslowtext", "cr820_statushightext"),
        "solicitation_type": pick("cr820_solicitationname", "cr820_solicitationtype"),
        "scope_text":        scope_text,
        "has_attachments":   header.get("oa_attachment") in (True, "Yes", "true", "YES"),
        "debug_keys":        list(header.keys()),
    }

    return cleaned


#
# 2. ATTACHMENTS LOOKUP
#
def build_attachments_query_url(rfq_header_id: str) -> str:
    """
    Guessed Dataverse collection name: cr820_rfqattachments
    Guessed FK: _cr820_rfqheaderid_value (typical pattern)
    We request * so we can see what fields are actually there.
    """
    # We try the most likely FK column naming pattern.
    # If this 400s, we'll inspect the debug response.
    raw_filter = f"_cr820_rfqheaderid_value eq {rfq_header_id!r}"

    params = {
        "$filter": raw_filter,
        "$select": "*",
    }
    return BASE_URL_ATTACH + "?" + urllib.parse.urlencode(params, safe="$, '")


@router.get("/columbus_detail/{rfq_header_id}/attachments")
async def get_rfq_attachments(rfq_header_id: str):
    """
    Returns a list of attachment metadata (filename, url-ish field if present).
    If the guess doesn't work, returns error/debug so we can refine the FK name.
    """
    url = build_attachments_query_url(rfq_header_id)

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_browsery_headers())

    if resp.status_code != 200:
        return {
            "error": "upstream_failed",
            "status_code": resp.status_code,
            "text": resp.text[:2000],
            "url": url,
        }

    data = resp.json()
    records = data.get("value", [])

    # We'll try to normalize to {filename, url} objects.
    out_files = []
    for rec in records:
        filename = (
            rec.get("cr820_filename")
            or rec.get("cr820_name")
            or "Attachment"
        )
        file_url = (
            rec.get("cr820_documenturl")
            or rec.get("cr820_document")
            or ""
        )
        out_files.append({
            "filename": filename,
            "url": file_url,
            "debug_rec_keys": list(rec.keys()),
        })

    return {
        "rfq_header_id": rfq_header_id,
        "count": len(out_files),
        "attachments": out_files,
        "debug_raw": records,
    }


#
# 3. LINE ITEMS LOOKUP
#
def build_items_query_url(rfq_header_id: str) -> str:
    """
    Guessed Dataverse collection name: cr820_rfqitems
    Guessed FK: _cr820_rfqheaderid_value
    We'll try to pull line number, description, qty, UOM.
    """
    raw_filter = f"_cr820_rfqheaderid_value eq {rfq_header_id!r}"

    params = {
        "$filter": raw_filter,
        "$select": "*",
    }
    return BASE_URL_ITEMS + "?" + urllib.parse.urlencode(params, safe="$, '")


@router.get("/columbus_detail/{rfq_header_id}/items")
async def get_rfq_items(rfq_header_id: str):
    """
    Returns a list of RFQ line items (line_no, name, desc, qty, uom).
    If the guess is wrong, you’ll still get debug info to inspect in console.
    """
    url = build_items_query_url(rfq_header_id)

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_browsery_headers())

    if resp.status_code != 200:
        return {
            "error": "upstream_failed",
            "status_code": resp.status_code,
            "text": resp.text[:2000],
            "url": url,
        }

    data = resp.json()
    records = data.get("value", [])

    out_lines = []
    for rec in records:
        out_lines.append({
            "line_no": rec.get("cr820_linenumber"),
            "name":    rec.get("cr820_itemname"),
            "desc":    rec.get("cr820_itemdescription"),
            "qty":     rec.get("cr820_qty"),
            "uom":     rec.get("cr820_uom"),
            "debug_rec_keys": list(rec.keys()),
        })

    return {
        "rfq_header_id": rfq_header_id,
        "count": len(out_lines),
        "items": out_lines,
        "debug_raw": records,
    }

@router.get("/columbus_debug/attachments_sample")
async def debug_attachments_sample():
    """
    Diagnostic endpoint:
    Ask the attachments entity for a small sample so we can see column names,
    especially the foreign key field that points back to cr820_rfqheaders.
    """
    params = {
        "$top": "5",
        "$select": "*",
    }
    url = BASE_URL_ATTACH + "?" + urllib.parse.urlencode(params, safe="$, '")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_browsery_headers())

    return {
        "status_code": resp.status_code,
        "text_preview": resp.text[:2000],
        "json": resp.json() if resp.status_code == 200 else None,
        "url": url,
    }


@router.get("/columbus_debug/items_sample")
async def debug_items_sample():
    """
    Diagnostic endpoint:
    Ask the items (line items) entity for a small sample so we can see its cols
    and figure out the proper FK field back to the header.
    """
    params = {
        "$top": "5",
        "$select": "*",
    }
    url = BASE_URL_ITEMS + "?" + urllib.parse.urlencode(params, safe="$, '")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_browsery_headers())

    return {
        "status_code": resp.status_code,
        "text_preview": resp.text[:2000],
        "json": resp.json() if resp.status_code == 200 else None,
        "url": url,
    }
