import json
import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.session import get_current_user_email
from app.core.db_core import engine
from app.services.document_processor import DocumentProcessor
from app.services.company_profile_template import merge_company_profile_defaults
from app.ai.client import get_llm_client
from app.storage import read_storage_bytes

router = APIRouter(prefix="/api/opportunities", tags=["opportunity-generate"])


async def _require_user(request: Request):
    email = get_current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT id, email, team_id FROM users WHERE email = :e LIMIT 1",
            {"e": email},
        )
        row = res.first()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    m = row._mapping
    return {"id": m["id"], "email": m["email"], "team_id": m.get("team_id")}


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
    except Exception:
        pass
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


def _build_doc_prompt(extracted: Dict[str, Any], company: Dict[str, Any], instructions_text: str = "") -> list[dict]:
    instr = instructions_text or extracted.get("submission_instructions") or ""
    today_str = datetime.date.today().strftime("%B %d, %Y")
    contact = _contact_from_extracted(extracted or {})
    return [
        {"role": "system", "content": "You are an expert proposal writer. Generate concise submission artifacts."},
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

Generate JSON:
{{
  "cover_letter": "text following the provided cover letter layout",
  "soq": {{
     "cover_page": "filled cover page lines",
     "company_overview": "Company overview text",
     "legal_structure": "entity type",
     "business_certifications": "MBE/WBE/SBE/EDGE or none",
     "programs_served": "list text",
     "criminal_history_policy": "text",
     "recordkeeping_controls": "text",
     "project_manager": "name/title/experience/certs",
     "key_personnel": "list text with credentials/training",
     "organizational_capacity": "text about capacity and timelines",
     "relevant_projects": "three projects with customer/address/phone/description/year",
     "low_income_programs": "list with details",
     "timelines": "ability to meet required timeframes",
     "contractor_licenses": "list",
     "trainings_completed": "list",
     "certifications": "list",
     "training_plan": "plan if gaps",
     "insurance": "coverage details + additional insured statement",
     "compliance_statements": "bullets acknowledging required clauses",
     "appendices": "list of appendices A-F as requested"
  }},
  "submission_instructions": "clear steps for email/portal/address, formatting, copies, attachments",
  "submission_checklist": ["ordered list of submission items with limits/addresses/email"],
  "calendar_events": [
     {{"title": "Proposal Due", "due_date": "<iso date if known>", "notes": ""}},
     {{"title": "Questions Due", "due_date": "<iso date if known>", "notes": ""}}
  ]
}}
Keep it concise, actionable, and grounded in the extracted data. If a date is unknown, leave it blank.
Cover letter must follow this exact layout (no placeholders left blank):
[Company Letterhead or Company Name]
[Company Address]
[City, State ZIP]
[Phone Number]
[Email Address]
[Website]

[Date]

[Agency Name]
[Contact Name, if provided]
[Agency Address]
[City, State ZIP]

Re: [Opportunity Title]

Dear [Contact Name or “Evaluation Committee”],

[Company Name] is pleased to submit our Statement of Qualifications in response to the “[Opportunity Title]” issued by [Agency Name]. Our firm is fully qualified and prepared to deliver the required services outlined in the solicitation, including:
• top 3–5 scope items from the RFP
• compliance/certification requirements
• required delivery timelines

As a [entity type], we acknowledge and accept full responsibility for performing all required services in accordance with the project specifications, applicable standards, and all local, state, and federal requirements.

We appreciate the opportunity to participate and look forward to contributing to the success of your program. Please contact me directly if further information is needed.

Sincerely,
[Authorized Representative Name]
[Title]
[Company Name]

Fill every bracketed field using extracted RFP data and company profile; do not leave placeholders.
SOQ must follow the 8 sections provided (cover page, company overview & profile, personnel, relevant experience, training & certifications, insurance, compliance statements, appendices). Checklist must include insurance limits and submission address/email if provided.
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
async def generate_submission_docs(opportunity_id: str, payload: dict | None = None, user=Depends(_require_user)):
    async with engine.begin() as conn:
        res = await conn.exec_driver_sql(
            "SELECT json_blob FROM opportunities WHERE id = :oid LIMIT 1",
            {"oid": opportunity_id},
        )
        row = res.first()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No extracted JSON found for this opportunity")

    try:
        extracted = row[0] if isinstance(row[0], dict) else json.loads(row[0])
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

    return {"opportunity_id": opportunity_id, "documents": data}


@router.get("/{opportunity_id}/extracted")
async def get_extracted_json(opportunity_id: str, user=Depends(_require_user)):
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
