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


def _build_doc_prompt(extracted: Dict[str, Any], company: Dict[str, Any], instructions_text: str = "", section_instructions: Dict[str, str] = None) -> list[dict]:
    instr = _sanitize_text(instructions_text) or _sanitize_text(extracted.get("submission_instructions", ""))
    today_str = datetime.date.today().strftime("%B %d, %Y")
    contact = _contact_from_extracted(extracted or {})
    section_instructions = section_instructions or {}

    # Get narrative sections (what AI should generate)
    narrative_sections = extracted.get("narrative_sections", [])
    if not narrative_sections:
        discovery = extracted.get("discovery", {}) if isinstance(extracted, dict) else {}
        narrative_sections = discovery.get("narrative_sections", [])

    # Get scope for context if no narratives found
    scope = extracted.get("scope_of_work", "") or extracted.get("summary", "")

    # If still empty, create smart defaults based on scope
    if not narrative_sections:
        narrative_sections = [
            {"name": "Company Qualifications", "requirements": f"Describe relevant experience and qualifications for: {scope[:300]}"},
            {"name": "Technical Approach", "requirements": f"Explain methodology and approach to deliver: {scope[:300]}"},
            {"name": "Project Understanding", "requirements": "Demonstrate understanding of the scope and requirements"},
        ]

    # Build detailed section instructions
    sections_to_generate = []
    for section in narrative_sections:
        if isinstance(section, dict):
            name = section.get("name", "")
            reqs = section.get("requirements", "Provide detailed response")
            page_limit = section.get("page_limit")
            word_limit = section.get("word_limit")

            limit_note = ""
            if page_limit:
                limit_note = f" (LIMIT: {page_limit} pages)"
            elif word_limit:
                limit_note = f" (LIMIT: {word_limit} words)"

            # Check for user-provided section-specific instructions
            section_key = name.lower().replace(" ", "_").replace("'", "")
            section_key_alt = re.sub(r"[^a-z0-9]+", "_", name.lower())
            user_context = section_instructions.get(section_key) or section_instructions.get(section_key_alt) or ""
            user_note = f" USER CONTEXT: {user_context}" if user_context else ""

            sections_to_generate.append(f'"{name}": "Address: {reqs}{limit_note}{user_note}"')
        elif isinstance(section, str):
            section_key = re.sub(r"[^a-z0-9]+", "_", section.lower())
            user_context = section_instructions.get(section_key) or ""
            user_note = f" USER CONTEXT: {user_context}" if user_context else ""
            sections_to_generate.append(f'"{section}": "Provide detailed response{user_note}"')

    sections_json = ",\n    ".join(sections_to_generate)

    # Get forms list for checklist
    forms = extracted.get("attachments_forms", []) or extracted.get("required_forms", [])
    forms_list = ", ".join(forms[:10]) if forms else "W-9, Insurance Certificate, required forms"

    # Build list of section names for checklist
    section_names = [s.get("name", "") if isinstance(s, dict) else s for s in narrative_sections]
    section_names_list = ", ".join(f'"{n}"' for n in section_names if n)

    return [
        {
            "role": "system",
            "content": """You are an expert government proposal writer with 20+ years experience winning contracts.

Your task: Generate complete, submission-ready proposal content for EACH requested section.

CRITICAL RULES:
- Write REAL, substantive content - never placeholders like "[Company Name]" or "[Insert details]"
- Use the actual company name and details from the profile provided
- Each narrative section must be 2-4 well-developed paragraphs
- Tailor content specifically to THIS RFP's requirements
- Professional tone matching government solicitation expectations
- Use EXACT section names as JSON keys (preserve spaces and capitalization)""",
        },
        {
            "role": "user",
            "content": f"""
=== RFP DETAILS ===
{json.dumps(extracted, indent=2)}

=== YOUR COMPANY PROFILE ===
{json.dumps(company, indent=2)}

=== SUBMISSION INSTRUCTIONS ===
{instr[:6000]}

=== CONTEXT ===
Today's Date: {today_str}
Agency Contact: {json.dumps(contact, indent=2)}

=== GENERATE THIS JSON ===
{{
  "response_sections": {{
    {sections_json}
  }},

  "submission_checklist": [
    {section_names_list},
    "{forms_list}"
  ],

  "calendar_events": [
    {{"title": "Event from RFP", "due_date": "YYYY-MM-DD", "notes": "Details"}}
  ]
}}

CRITICAL REQUIREMENTS:
1. Use the ACTUAL company name from the profile (not "[Company Name]")
2. Reference the ACTUAL RFP title and agency in each section
3. Include SPECIFIC past project examples if available in company profile
4. Each response section needs SUBSTANCE - minimum 2-4 paragraphs
5. Use the EXACT section names as JSON keys (e.g., "Brief Narrative" not "brief_narrative")
6. If USER CONTEXT is provided for a section, incorporate that specific information
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
    section_instructions = {}
    try:
        instruction_upload_ids = (payload or {}).get("instruction_upload_ids") or []
        section_instructions = (payload or {}).get("section_instructions") or {}
    except Exception:
        instruction_upload_ids = []
        section_instructions = {}
    llm = get_llm_client()
    if not llm:
        raise HTTPException(status_code=500, detail="LLM client unavailable")

    instructions_text = await _load_instruction_text(user["id"], instruction_upload_ids)
    prompt = _build_doc_prompt(extracted, company_profile, instructions_text, section_instructions)
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
