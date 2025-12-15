import asyncio
import json
import datetime
import logging
import re
import time
from typing import Any, Dict
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.company_profile_template import merge_company_profile_defaults
from app.ai.client import get_llm_client
from app.storage import read_storage_bytes, create_presigned_get, store_bytes
from app.api.auth_helpers import ensure_user_can_access_opportunity, require_user_with_team
from app.services.response_library import ResponseLibrary

router = APIRouter(prefix="/api/opportunities", tags=["opportunity-generate"])

response_lib = ResponseLibrary()
_rl_requests = defaultdict(deque)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 6  # per user per window
MAX_UPLOAD_IDS = 10
MAX_INSTRUCTION_BYTES = 1_000_000  # 1 MB cap for instruction text
MAX_PROMPT_JSON_CHARS = 20000
MAX_INSTR_CHARS = 6000
DEFAULT_TEMPERATURE = 0.4


async def _get_company_profile(user_id: Any) -> Dict[str, Any]:
    try:
        async with engine.begin() as conn:
            res = await conn.exec_driver_sql(
                "SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1",
                {"uid": user_id},
            )
            row = res.first()
            if row and row[0]:
                raw = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                merged = merge_company_profile_defaults(raw)

                file_fields = [
                    # Commonly used signature and compliance files
                    "signature_image",
                    "digital_signature",
                    "capability_statement",
                    "insurance_certificate",
                    "bonding_letter",
                    "w9_upload",
                    "business_license",
                    # Additional uploads supported by the account page
                    "ohio_certificate",
                    "cert_upload",
                    "product_catalogs",
                    "ref1_letter",
                    "ref2_letter",
                    "ref3_letter",
                    "ref4_letter",
                    "ref5_letter",
                    "sub1_certificate",
                    "sub2_certificate",
                    "sub3_certificate",
                    "sub4_certificate",
                    "sub5_certificate",
                    "price_list_upload",
                    "safety_sheets",
                    "warranty_info",
                    "previous_contracts",
                    "org_chart",
                    "financial_statements",
                    "debarment_certification",
                    "labor_compliance_cert",
                    "conflict_of_interest",
                    "references_combined",
                ]

                for field in file_fields:
                    storage_key = merged.get(field)
                    if not storage_key or not isinstance(storage_key, str):
                        continue
                    # Skip invalid storage keys (e.g., stringified UploadFile objects)
                    if storage_key.startswith("UploadFile(") or storage_key.startswith("<"):
                        logging.warning("Invalid storage key for %s: %s", field, storage_key[:50])
                        continue
                    url = None
                    try:
                        url = create_presigned_get(storage_key)
                    except Exception:
                        logging.warning("Could not create presigned URL for %s", field)
                    if url:
                        merged[f"{field}_url"] = url
                        logging.info("Created presigned URL for %s: %s...", field, url[:50])
                    filename = merged.get(f"{field}_name", "")
                    if filename:
                        merged[f"{field}_filename"] = filename
                return merged
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


def _check_rate_limit(user_id: Any) -> None:
    now = time.time()
    dq = _rl_requests[user_id]
    while dq and dq[0] < now - RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many generate requests. Please wait and try again.")
    dq.append(now)


def _sanitize_text(val: str, max_chars: int = 8000) -> str:
    if not val:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", val)
    # Remove obvious prompt injection markers
    cleaned = cleaned.replace("<<", "").replace(">>", "")
    return cleaned[:max_chars]


def _truncate_json_for_prompt(obj: Any, max_chars: int) -> str:
    try:
        txt = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        txt = "{}"
    if len(txt) > max_chars:
        txt = txt[:max_chars] + "...(truncated)"
    return txt


def _build_doc_prompt(
    extracted: Dict[str, Any],
    company: Dict[str, Any],
    instructions_text: str = "",
    section_instructions: Dict[str, str] | None = None,
) -> list[dict]:
    instr = _sanitize_text(instructions_text, max_chars=MAX_INSTR_CHARS) or _sanitize_text(
        extracted.get("submission_instructions", ""), max_chars=MAX_INSTR_CHARS
    )
    today_str = datetime.date.today().strftime("%B %d, %Y")
    contact = _contact_from_extracted(extracted or {})
    section_instructions = section_instructions or {}

    # Get narrative sections with their requirements
    narrative_sections = extracted.get("narrative_sections", [])
    if not narrative_sections:
        discovery = extracted.get("discovery", {}) if isinstance(extracted, dict) else {}
        narrative_sections = discovery.get("narrative_sections", [])

    sections_to_generate = []
    for section in narrative_sections:
        if isinstance(section, dict):
            name = section.get("name", "")
            reqs = section.get("requirements", "Provide detailed response")
            page_limit = section.get("page_limit")
            word_limit = section.get("word_limit")

            limit_note = ""
            if page_limit:
                limit_note = f" (max {page_limit} pages)"
            elif word_limit:
                limit_note = f" (max {word_limit} words)"

            sections_to_generate.append({
                "name": name,
                "requirements": reqs,
                "limit": limit_note,
            })
        elif isinstance(section, str):
            sections_to_generate.append({
                "name": section,
                "requirements": "Provide detailed response",
                "limit": "",
            })

    # If still empty, derive from scope of work
    if not sections_to_generate:
        scope = extracted.get("scope_of_work", "") or ""
        sections_to_generate = [
            {
                "name": "Cover Letter",
                "requirements": "Professional introduction referencing the specific opportunity",
                "limit": "",
            },
            {
                "name": "Company Qualifications",
                "requirements": f"Relevant experience and qualifications for: {scope[:200]}",
                "limit": "",
            },
            {
                "name": "Technical Approach",
                "requirements": f"Methodology and approach to deliver: {scope[:200]}",
                "limit": "",
            },
        ]

    sections_json_parts = []
    section_names = []
    context_lines = []
    for s in sections_to_generate:
        name = s["name"]
        reqs = s["requirements"]
        limit = s["limit"]
        key = name.lower().replace(" ", "_").replace("'", "")
        key_alt = re.sub(r"[^a-z0-9]+", "_", name.lower())
        user_context = section_instructions.get(key) or section_instructions.get(key_alt) or ""
        if user_context:
            safe_context = user_context.replace("\\", "\\\\").replace('"', '\\"')
            user_note = f"MUST INCLUDE USER CONTEXT: {safe_context}. Then address: {reqs}{limit}"
            context_lines.append(f'- {name}: {safe_context}')
        else:
            user_note = f"Address: {reqs}{limit}"
        section_names.append(name)
        sections_json_parts.append(
            f'    "{name}": "{user_note}"'
        )
    sections_json = ",\n".join(sections_json_parts)
    section_names_list = ", ".join(f'"{n}"' for n in section_names if n)
    user_context_block = "\n".join(context_lines) if context_lines else "None provided."

    extracted_json = _truncate_json_for_prompt(extracted, MAX_PROMPT_JSON_CHARS)
    company_json = _truncate_json_for_prompt(company, MAX_PROMPT_JSON_CHARS)
    signature_url = (
        company.get("signature_image_url")
        or company.get("digital_signature_url")
        or ""
    )
    signatory = company.get("authorized_signatory") or {}
    primary_contact = company.get("primary_contact") or {}
    signature_name = signatory.get("name") or primary_contact.get("name") or ""
    signature_title = signatory.get("title") or primary_contact.get("title") or ""
    if isinstance(signature_name, str):
        signature_name = signature_name.strip()
    if isinstance(signature_title, str):
        signature_title = signature_title.strip()
    signature_block = (
        f"""
SIGNATURE AVAILABLE:
- Image URL: {signature_url}
- Signatory Name: {signature_name}
- Title: {signature_title}
""".strip()
        if signature_url
        else "SIGNATURE AVAILABLE: None provided."
    )

    return [
        {
            "role": "system",
            "content": """You are an expert government proposal writer with 20+ years of experience winning contracts. 
Generate professional, compliant, and compelling proposal content.
Write substantive content - never use placeholders or generic filler.
Tailor every section to the specific RFP requirements and company qualifications.
When a signature asset is available, incorporate it into cover letters using the provided HTML block.""",
        },
        {
            "role": "user",
            "content": f"""
RFP REQUIREMENTS:
{extracted_json}

COMPANY PROFILE:
{company_json}

SIGNATURE DETAILS:
{signature_block}

SUBMISSION INSTRUCTIONS:
{instr[:6000]}

TODAY'S DATE: {today_str}

AGENCY CONTACT:
{json.dumps(contact, indent=2)}

USER CONTEXT PROVIDED (per section):
{user_context_block}

Generate a complete proposal response with this EXACT JSON structure:
{{
  "response_sections": {{
{sections_json}
  }},
  
  "submission_checklist": [
    {section_names_list}
  ],
  "calendar_events": [{{"title": "Event name", "due_date": "YYYY-MM-DD", "notes": "Details"}}]
}}

REQUIREMENTS:
1. OUTPUT FORMAT: Each response section must be HTML-formatted for professional display:
   - Use <h2>Section Title</h2> for main headings
   - Use <h3>Subsection</h3> for sub-points
   - Wrap paragraphs in <p>...</p> tags
   - Use <ul><li>...</li></ul> for bullet lists
   - Use <strong>Company Name</strong> for emphasis on key terms
   - Use <em>...</em> for certifications and titles

2. STRUCTURE: Each section should include:
   - Opening paragraph introducing the topic
   - 2-3 supporting paragraphs with specific details
   - Bullet list of key qualifications or deliverables where appropriate
   - Closing paragraph with commitment statement
   - FOR COVER LETTERS: include the signature block at the bottom when a signature is available

3. SIGNATURE: If signature_image_url is provided in the company profile, include it in transmittal/cover letters:
   - Add after "Sincerely," and before the signatory's name
   - Format: <img src="{signature_url}" alt="Signature" style="max-width: 200px; height: auto; margin: 10px 0;">
   - Example:
     Sincerely,<br><br>
     <img src="{signature_url}" alt="Signature" style="max-width: 200px; height: auto; margin: 10px 0;"><br>
     <strong>{signature_name}</strong><br>
     {company.get('legal_name', '')}

4. CONTENT:
   - Use specific details from the company profile (names, experience, certifications)
   - Match the RFP's tone and address stated requirements
   - Include concrete examples of relevant past projects
   - Reference specific certifications, years of experience, team members

5. Submission checklist must include ALL narrative/form items required for submission
6. Use the EXACT section names as JSON keys (preserve spaces and capitalization)
7. If USER CONTEXT is provided for a section, incorporate that specific information prominently
""".strip(),
        },
    ]


async def _load_instruction_text(user_id: Any, upload_ids: list[int]) -> str:
    if not upload_ids:
        return ""
    ids = list(upload_ids)[:MAX_UPLOAD_IDS]
    placeholders = ",".join([f":id{i}" for i in range(len(ids))])
    params = {f"id{i}": uid for i, uid in enumerate(ids)}
    params["uid"] = user_id

    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            f"SELECT id, storage_key, mime, filename, size FROM user_uploads WHERE user_id = :uid AND id IN ({placeholders})",
            params,
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    processor = DocumentProcessor()
    chunks: list[str] = []
    total_bytes = 0
    for rec in rows:
        try:
            size = rec.get("size") or 0
            total_bytes += size
            if total_bytes > MAX_INSTRUCTION_BYTES:
                break
            data = await asyncio.to_thread(read_storage_bytes, rec.get("storage_key"))
            if not data:
                continue
            extraction = processor.extract_text(data, rec.get("mime"), rec.get("filename"))
            txt = extraction.get("text") or ""
            if txt:
                chunks.append(txt[:MAX_INSTR_CHARS])
        except Exception:
            continue
    return "\n\n".join(chunks)[:MAX_INSTR_CHARS]


@router.post("/{opportunity_id}/generate")
async def generate_submission_docs(opportunity_id: str, payload: dict | None = None, user=Depends(require_user_with_team)):
    _check_rate_limit(user.get("id"))
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
    section_instructions: Dict[str, str] = {}
    try:
        instruction_upload_ids = (payload or {}).get("instruction_upload_ids") or []
        section_instructions = (payload or {}).get("section_instructions") or {}
    except Exception:
        instruction_upload_ids = []
        section_instructions = {}

    llm = get_llm_client()
    if not llm:
        raise HTTPException(status_code=503, detail="LLM client unavailable")

    instructions_text = await _load_instruction_text(user["id"], instruction_upload_ids)
    prompt = _build_doc_prompt(extracted, company_profile, instructions_text, section_instructions)
    try:
        resp = llm.chat(prompt, temperature=DEFAULT_TEMPERATURE, format="json")
        data = json.loads(resp)
        if not isinstance(data, dict) or "response_sections" not in data:
            raise ValueError("Invalid LLM response")
    except Exception as exc:
        logging.error("LLM generation failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="AI generation failed. Please try again.")

    return {
        "opportunity_id": opportunity_id,
        "documents": data,
        "signature_url": company_profile.get("signature_image_url"),
        "company_profile": company_profile,
    }


class RefineRequest(BaseModel):
    content: str
    action: str  # "improve", "shorten", or "expand"
    section_name: str | None = None


@router.post("/{opportunity_id}/refine")
async def refine_content(opportunity_id: str, payload: RefineRequest, request: Request, user=Depends(require_user_with_team)):
    """Refine content using AI - improve, shorten, or expand."""
    await ensure_user_can_access_opportunity(user, opportunity_id)
    _check_rate_limit(user.get("id"))

    action = (payload.action or "").lower()
    if action not in ("improve", "shorten", "expand"):
        raise HTTPException(status_code=400, detail="Invalid action. Use: improve, shorten, or expand")

    content = _sanitize_text(payload.content, max_chars=15000)
    if not content.strip():
        raise HTTPException(status_code=400, detail="No content to refine")

    prompts = {
        "improve": """Improve the following RFP response text. Make it more professional,
clear, and compelling while preserving the key information and meaning.
Keep the same approximate length. Return ONLY the improved text, no explanations.""",
        "shorten": """Shorten the following RFP response text by approximately 30-40%.
Remove redundancy and verbose language while keeping all essential information.
Maintain a professional tone. Return ONLY the shortened text, no explanations.""",
        "expand": """Expand the following RFP response text by approximately 30-50%.
Add more detail, examples, and supporting information while maintaining accuracy.
Keep a professional tone. Return ONLY the expanded text, no explanations.""",
    }

    system_prompt = prompts[action]
    user_prompt = f"Text to {action}:\n\n{content}"

    try:
        llm = get_llm_client()
        if not llm:
            raise HTTPException(status_code=503, detail="LLM client unavailable")

        result = await asyncio.to_thread(
            llm.chat,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        refined_text = (result or "").strip()
        if not refined_text:
            raise HTTPException(status_code=500, detail="AI returned empty response")

        return {"refined_content": refined_text, "action": action}

    except HTTPException:
        raise
    except Exception as exc:
        logging.error("Refine error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{opportunity_id}/save-package")
async def save_package_to_folder(
    opportunity_id: str,
    payload: dict | None = None,
    user=Depends(require_user_with_team),
):
    """Save the generated package as a document to the opportunity folder."""
    await ensure_user_can_access_opportunity(user, opportunity_id)

    content = (payload or {}).get("content", "")
    filename = (payload or {}).get("filename", f"proposal-{opportunity_id}.html")

    if not content:
        raise HTTPException(status_code=400, detail="No content to save")

    data = content.encode("utf-8")
    try:
        storage_key, size, mime = store_bytes(
            user["id"],
            opportunity_id,
            data,
            filename,
            "text/html",
        )
    except Exception as exc:
        logging.error("Failed to store generated package: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save package")

    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            """
            INSERT INTO user_uploads (user_id, opportunity_id, filename, mime, size, storage_key, source_note)
            VALUES (:uid, :oid, :fn, :mime, :size, :key, 'ai-studio-generated')
            """,
            {
                "uid": user["id"],
                "oid": opportunity_id,
                "fn": filename,
                "mime": mime,
                "size": size,
                "key": storage_key,
            },
        )

    return {"ok": True, "filename": filename, "size": size}


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
