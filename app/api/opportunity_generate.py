import json
import datetime
import logging
import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.company_profile_template import merge_company_profile_defaults
from app.ai.client import get_llm_client
from app.storage import read_storage_bytes
from app.api.auth_helpers import ensure_user_can_access_opportunity, require_user_with_team
from app.services.response_library import ResponseLibrary

router = APIRouter(prefix="/api/opportunities", tags=["opportunity-generate"])

response_lib = ResponseLibrary()

async def _get_company_profile(user_id: Any) -> Dict[str, Any]:
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                "SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1",
                {"uid": user_id},
            )
            row = res.first()
            if row and row[0]:
                data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                return merge_company_profile_defaults(data)
    except Exception as exc:
        logging.warning("Failed to load company profile: %s", exc)
    return merge_company_profile_defaults({})


def _contact_from_extracted(extracted: Dict[str, Any]) -> Dict[str, str]:
    contact = {
        "name": "",
        "title": "",
        "phone": "",
        "email": "",
        "address": extracted.get("agency_address", "") if isinstance(extracted, dict) else "",
        "city_state_zip": "",
    }
    contacts = extracted.get("contacts") if isinstance(extracted, dict) else None
    if isinstance(contacts, list):
        for c in contacts:
            if isinstance(c, dict):
                for k in contact.keys():
                    if k in c and c.get(k):
                        contact[k] = c.get(k) or contact[k]
                break
            elif isinstance(c, str) and c.strip():
                contact["name"] = c.strip()
                break
    return contact


def _sanitize_text(val: str, max_chars: int = 8000) -> str:
    if not val:
        return ""
    # Strip control chars and trim length
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", val)
    return cleaned[:max_chars]


def _build_doc_prompt(extracted: Dict[str, Any], company: Dict[str, Any], instructions_text: str = "") -> list[dict]:
    instr = _sanitize_text(instructions_text) or _sanitize_text(extracted.get("submission_instructions", ""))
    today_str = datetime.date.today().strftime("%B %d, %Y")
    contact = _contact_from_extracted(extracted or {})

    # Get required sections from discovery, or use defaults
    discovery = extracted.get("discovery", {}) if isinstance(extracted, dict) else {}
    required_sections = discovery.get("required_response_sections", [])

    # Build dynamic document sections based on what RFP requires
    if not required_sections:
        # Fallback: infer from required_documents
        required_docs = extracted.get("required_documents", []) if isinstance(extracted, dict) else []
        required_sections = required_docs if required_docs else ["Cover Letter", "Statement of Qualifications"]

    # Create dynamic response structure based on required sections
    dynamic_sections = {}
    for section in required_sections:
        section_key = section.lower().replace(" ", "_").replace("-", "_")
        dynamic_sections[section_key] = f"Content for {section}"

    return [
        {
            "role": "system",
            "content": "You are an expert proposal writer. Generate professional, compliant submission documents tailored to the RFP requirements.",
        },
        {
            "role": "user",
            "content": f"""
Extracted RFP JSON:
{json.dumps(extracted, indent=2)}

Company Profile:
{json.dumps(company, indent=2)}

RFP Instructions (verbatim, prioritize compliance):
{instr[:8000]}

Use today's date: {today_str}
Best available contact/address from extraction:
{json.dumps(contact, indent=2)}

The RFP requires these response sections: {json.dumps(required_sections)}

Generate JSON with this structure:
{{
  "cover_letter": "Professional cover letter text",
  "response_sections": {{
    // Generate a key for EACH required section
    // Example: "technical_approach": "content...",
    // Example: "past_performance": "content...",
    // Example: "pricing": "content...",
  }},
  "submission_instructions": "Clear steps for submission",
  "submission_checklist": ["Ordered list of items to submit with page limits/requirements"],
  "calendar_events": [
    {{"title": "Proposal Due", "due_date": "<iso date>", "notes": ""}},
    {{"title": "Questions Due", "due_date": "<iso date>", "notes": ""}}
  ],
  "required_sections_list": {json.dumps(required_sections)}
}}

IMPORTANT:
- Generate content for EVERY section in required_sections_list
- Cover letter must be professional and reference the specific opportunity
- Each response section should be substantive (2-4 paragraphs minimum)
- Use company profile data to personalize the response
- Checklist must match the RFP's submission requirements exactly
""".strip(),
        },
    ]


async def _load_instruction_text(user_id: Any, upload_ids: list[int]) -> str:
    if not upload_ids:
        return ""
    processor = DocumentProcessor()
    chunks: list[str] = []
    for uid in upload_ids:
        try:
            async with engine.begin() as conn:
                res = await conn.exec_driver_sql(
                    "SELECT storage_key, mime, filename FROM user_uploads WHERE id = :id AND user_id = :uid",
                    {"id": uid, "uid": user_id},
                )
                row = res.first()
            if not row:
                continue
            rec = dict(row._mapping)
            data = read_storage_bytes(rec["storage_key"])
            if not data:
                continue
            extraction = processor.extract_text(data, rec.get("mime"), rec.get("filename"))
            txt = extraction.get("text") or ""
            if txt:
                chunks.append(txt)
        except Exception:
            continue
    return "\n\n".join(chunks)


@router.post("/{opportunity_id}/generate")
async def generate_submission_docs(opportunity_id: str, payload: dict | None = None, user=Depends(require_user_with_team)):
    await ensure_user_can_access_opportunity(user, opportunity_id)
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT json_blob FROM opportunities WHERE id = :oid LIMIT 1",
            {"oid": opportunity_id},
        )
        row = res.first()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No extracted JSON found for this opportunity")

    try:
        blob = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        if isinstance(blob, dict) and "extracted" in blob:
            extracted = blob.get("extracted") or {}
        else:
            extracted = blob
    except Exception:
        extracted = {}

    company_profile = await _get_company_profile(user["id"])
    instruction_upload_ids = []
    try:
        instruction_upload_ids = (payload or {}).get("instruction_upload_ids") or []
    except Exception:
        instruction_upload_ids = []
    llm = get_llm_client()
    if not llm:
        raise HTTPException(status_code=500, detail="LLM client unavailable")

    instructions_text = await _load_instruction_text(user["id"], instruction_upload_ids)
    prompt = _build_doc_prompt(extracted, company_profile, instructions_text)
    try:
        resp = llm.chat(prompt, temperature=0.4, format="json")
        data = json.loads(resp)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}")

    # store generated answers in response library for reuse (question/answer pairs)
    try:
        if data and isinstance(data, dict):
            # we only store the cover letter for now
            cover = data.get("cover_letter") or ""
            if cover:
                await response_lib.store_response(
                    user,
                    question="Cover letter",
                    answer=cover,
                    metadata={"opportunity_id": opportunity_id, "type": "cover_letter"},
                )
    except Exception:
        pass

    return {"opportunity_id": opportunity_id, "documents": data}


@router.get("/{opportunity_id}/extracted")
async def get_extracted_json(opportunity_id: str, user=Depends(require_user_with_team)):
    await ensure_user_can_access_opportunity(user, opportunity_id)
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            """
            SELECT id, title, agency_name, summary, json_blob, due_date
            FROM opportunities
            WHERE id = :oid
            LIMIT 1
            """,
            {"oid": opportunity_id},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    try:
        blob = row._mapping["json_blob"]
        extracted = blob if isinstance(blob, dict) else json.loads(blob)
    except Exception:
        extracted = {}
    return {
        "id": row._mapping["id"],
        "title": row._mapping["title"],
        "agency": row._mapping["agency_name"],
        "summary": row._mapping["summary"],
        "due_date": row._mapping["due_date"],
        "extracted": extracted,
    }
