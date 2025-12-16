import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth_helpers import require_user_with_team
from app.core.db_core import engine
from app.ai.client import get_llm_client
from app.services.company_profile_template import merge_company_profile_defaults

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# Token/character limits
MAX_CONTEXT_CHARS = 100000  # ~25k tokens worth of document text
MAX_HISTORY_MESSAGES = 10


class ChatRequest(BaseModel):
    session_id: int
    message: str


@router.get("/{session_id}/messages")
async def get_chat_messages(session_id: int, user=Depends(require_user_with_team)) -> List[Dict[str, Any]]:
    """Get all chat messages for a session."""
    async with engine.begin() as conn:
        session = await conn.exec_driver_sql(
            """
            SELECT id FROM ai_studio_sessions 
            WHERE id = :id AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": session_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        if not session.first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        res = await conn.exec_driver_sql(
            """
            SELECT id, role, content, created_at 
            FROM ai_chat_messages 
            WHERE session_id = :session_id 
            ORDER BY created_at ASC
            """,
            {"session_id": session_id},
        )
        return [dict(r._mapping) for r in res.fetchall()]


@router.post("/message")
async def send_chat_message(req: ChatRequest, user=Depends(require_user_with_team)) -> Dict[str, Any]:
    """Send a message and get AI response based on full RFP document."""

    async with engine.begin() as conn:
        # 1. Get session with full state
        session = await conn.exec_driver_sql(
            """
            SELECT s.id, s.state_json, s.opportunity_id
            FROM ai_studio_sessions s
            WHERE s.id = :id AND (s.user_id = :uid OR (s.team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": req.session_id, "uid": user["id"], "team_id": user.get("team_id")},
        )
        row = session.first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = json.loads(row.state_json or "{}")

        # 2. Save user message
        await conn.exec_driver_sql(
            """
            INSERT INTO ai_chat_messages (session_id, user_id, role, content)
            VALUES (:session_id, :user_id, 'user', :content)
            """,
            {"session_id": req.session_id, "user_id": user["id"], "content": req.message},
        )

        # 3. Get chat history
        history = await conn.exec_driver_sql(
            """
            SELECT role, content FROM ai_chat_messages 
            WHERE session_id = :session_id 
            ORDER BY created_at DESC LIMIT :limit
            """,
            {"session_id": req.session_id, "limit": MAX_HISTORY_MESSAGES},
        )
        chat_history = [dict(r._mapping) for r in history.fetchall()][::-1]

        # 4. Get document context - prioritize raw_text, fall back to extracted
        extracted_state = state.get("extracted", {}) if isinstance(state, dict) else {}
        raw_text, extracted_data = _resolve_extracted_state(extracted_state)

        # Build context from raw text (primary) + extracted metadata (secondary)
        if raw_text and len(raw_text) > MAX_CONTEXT_CHARS:
            # Large document - find relevant chunks
            relevant_text = _find_relevant_chunks(raw_text, req.message)
            document_context = _build_document_context(relevant_text, extracted_data)
        else:
            document_context = _build_document_context(raw_text, extracted_data)

        # 5. Load company profile context
        company_profile = await _get_company_profile(conn, user["id"])
        company_context = _format_company_profile(company_profile)

        # 6. Call LLM
        llm = get_llm_client()
        if not llm:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service unavailable")

        system_prompt = f"""You are an expert assistant helping a company respond to an RFP (Request for Proposal).

You have access to:
1. The FULL TEXT of the RFP document
2. The user's COMPANY PROFILE with their qualifications, experience, and capabilities

=== COMPANY PROFILE START ===
{company_context}
=== COMPANY PROFILE END ===

=== RFP DOCUMENT START ===
{document_context}
=== RFP DOCUMENT END ===

INSTRUCTIONS:
1. Answer questions by finding relevant information from BOTH the RFP and the company profile
2. When asked about requirements, check if the company meets them based on their profile
3. When asked about qualifications or experience, reference the company's past projects, certifications, and key personnel
4. For questions like "do we qualify?" or "can we meet this requirement?" - compare RFP requirements against company capabilities
5. Be specific - quote exact RFP language and reference specific company qualifications
6. If the company profile doesn't have relevant info, mention what information might be needed
7. For strategic questions like "what should we highlight?" - identify the company's strengths that align with RFP evaluation criteria
8. Be helpful and thorough - these are important business documents"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)

        response = llm.chat(messages, temperature=0.2)

        # 7. Save assistant response
        res = await conn.exec_driver_sql(
            """
            INSERT INTO ai_chat_messages (session_id, user_id, role, content)
            VALUES (:session_id, :user_id, 'assistant', :content)
            RETURNING id, created_at
            """,
            {"session_id": req.session_id, "user_id": user["id"], "content": response},
        )
        new_row = res.first()

        return {
            "id": new_row.id,
            "role": "assistant",
            "content": response,
            "created_at": str(new_row.created_at),
        }


def _build_document_context(raw_text: str, extracted: Dict[str, Any]) -> str:
    """Build context prioritizing raw document text, with extracted metadata as supplement."""
    parts = []

    # Add extracted metadata summary at the top for quick reference
    meta_parts = []
    if extracted.get("title"):
        meta_parts.append(f"Title: {extracted['title']}")
    if extracted.get("agency"):
        meta_parts.append(f"Agency: {extracted['agency']}")
    if extracted.get("deadlines"):
        deadlines = extracted["deadlines"]
        if isinstance(deadlines, list) and deadlines:
            deadline_strs = []
            for d in deadlines[:5]:
                if isinstance(d, dict):
                    deadline_strs.append(f"{d.get('event', 'Event')}: {d.get('date', '')} {d.get('time', '')}")
                else:
                    deadline_strs.append(str(d))
            meta_parts.append("Key Deadlines: " + "; ".join(deadline_strs))

    if meta_parts:
        parts.append("## Quick Reference\n" + "\n".join(meta_parts))

    # Add the full document text (this is the key part!)
    if raw_text:
        # Truncate if too long, keeping beginning and end
        if len(raw_text) > MAX_CONTEXT_CHARS:
            half = MAX_CONTEXT_CHARS // 2
            truncated_text = raw_text[:half] + "\n\n[... middle section truncated for length ...]\n\n" + raw_text[-half:]
            parts.append("## Full Document Content\n" + truncated_text)
        else:
            parts.append("## Full Document Content\n" + raw_text)
    else:
        # Fall back to extracted data if no raw text
        if extracted.get("summary"):
            parts.append(f"## Summary\n{extracted['summary']}")
        if extracted.get("scope_of_work"):
            parts.append(f"## Scope of Work\n{extracted['scope_of_work']}")
        if extracted.get("submission_instructions"):
            parts.append(f"## Submission Instructions\n{extracted['submission_instructions']}")

        # Add narrative sections requirements
        if extracted.get("narrative_sections"):
            sections = extracted["narrative_sections"]
            if isinstance(sections, list) and sections:
                section_text = []
                for s in sections:
                    if isinstance(s, dict):
                        name = s.get("name", "Section")
                        reqs = s.get("requirements", "")
                        section_text.append(f"- {name}: {reqs}")
                    else:
                        section_text.append(f"- {s}")
                parts.append("## Required Sections\n" + "\n".join(section_text))

    if not parts:
        return "No document content available. Please extract the RFP first."

    return "\n\n".join(parts)


async def _get_company_profile(conn, user_id: str) -> Dict[str, Any]:
    """Fetch the user's company profile from the database."""
    try:
        res = await conn.exec_driver_sql(
            "SELECT data FROM company_profiles WHERE user_id = :uid LIMIT 1",
            {"uid": user_id},
        )
        row = res.first()
        if row and row[0]:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return merge_company_profile_defaults(data)
    except Exception as exc:
        logger.warning(f"Failed to load company profile: {exc}")
    return merge_company_profile_defaults({})


def _resolve_extracted_state(extracted_state: Any) -> tuple[str, Dict[str, Any]]:
    """
    Unwrap nested extracted payloads and collect raw_text if present at any level.

    The saved session state may look like:
    {ok, opportunity_id, extracted: {version, discovery, extracted: {...}, raw_text}}
    """
    raw_text = ""
    extracted_data: Dict[str, Any] = {}
    current = extracted_state if isinstance(extracted_state, dict) else {}

    while isinstance(current, dict):
        raw_text = raw_text or current.get("raw_text", "")
        nxt = current.get("extracted")
        if isinstance(nxt, dict):
            current = nxt
            continue
        extracted_data = current
        break

    return raw_text, extracted_data


def _format_company_profile(profile: Dict[str, Any]) -> str:
    """Format company profile into readable context for the LLM."""
    parts = []

    # Basic company info
    if profile.get("legal_name"):
        parts.append(f"Company Name: {profile['legal_name']}")
    if profile.get("entity_type"):
        parts.append(f"Entity Type: {profile['entity_type']}")
    if profile.get("hq_address"):
        parts.append(f"Address: {profile['hq_address']}")
    if profile.get("website"):
        parts.append(f"Website: {profile['website']}")
    if profile.get("service_area"):
        parts.append(f"Service Area: {profile['service_area']}")

    # Primary contact
    contact = profile.get("primary_contact", {})
    if contact.get("name"):
        contact_info = f"Primary Contact: {contact['name']}"
        if contact.get("title"):
            contact_info += f", {contact['title']}"
        if contact.get("email"):
            contact_info += f" ({contact['email']})"
        parts.append(contact_info)

    # Certifications (MBE, SBE, WBE, EDGE)
    certs = profile.get("certifications_status", {})
    active_certs = [c for c in ["MBE", "SBE", "EDGE", "WBE"] if certs.get(c)]
    if active_certs:
        parts.append(f"Certifications: {', '.join(active_certs)}")
    if certs.get("details"):
        parts.append(f"Certification Details: {certs['details']}")

    # Contractor licenses
    licenses = profile.get("contractor_licenses", [])
    valid_licenses = [lic for lic in licenses if lic.get("number")]
    if valid_licenses:
        lic_strs = []
        for lic in valid_licenses:
            lic_str = f"{lic.get('state', 'State')} #{lic.get('number', '')}"
            if lic.get("expiry"):
                lic_str += f" (exp: {lic['expiry']})"
            lic_strs.append(lic_str)
        parts.append(f"Contractor Licenses: {'; '.join(lic_strs)}")

    # Insurance
    insurance = profile.get("insurance", {})
    ins_parts = []
    if insurance.get("liability_insurance", {}).get("carrier"):
        liability = insurance["liability_insurance"]
        ins_parts.append(f"Liability: {liability['carrier']}, Limits: {liability.get('limits', 'N/A')}")
    if insurance.get("workers_comp_certificate", {}).get("id"):
        ins_parts.append("Workers Comp: Active")
    if ins_parts:
        parts.append(f"Insurance: {'; '.join(ins_parts)}")

    # Key personnel
    personnel = profile.get("key_personnel", [])
    valid_personnel = [p for p in personnel if p.get("name")]
    if valid_personnel:
        parts.append("\nKey Personnel:")
        for person in valid_personnel[:10]:
            person_str = f"  - {person['name']}"
            if person.get("role"):
                person_str += f" ({person['role']})"
            if person.get("bio"):
                person_str += f": {person['bio'][:200]}"
            parts.append(person_str)

    # Past projects
    projects = profile.get("recent_projects", [])
    valid_projects = [p for p in projects if p.get("client_name") or p.get("description")]
    if valid_projects:
        parts.append("\nPast Projects/Experience:")
        for proj in valid_projects[:10]:
            proj_str = f"  - {proj.get('client_name', 'Project')}"
            if proj.get("description"):
                proj_str += f": {proj['description'][:300]}"
            if proj.get("dates"):
                proj_str += f" ({proj['dates']})"
            parts.append(proj_str)

    # Training and certifications
    training = profile.get("training_and_certifications", [])
    valid_training = [t for t in training if t.get("person") and (t.get("certifications") or t.get("trainings_completed"))]
    if valid_training:
        parts.append("\nTraining & Certifications:")
        for t in valid_training[:5]:
            all_quals = (t.get("certifications", []) + t.get("trainings_completed", []))[:10]
            if all_quals:
                parts.append(f"  - {t['person']}: {', '.join(all_quals)}")

    # Low income program experience
    programs = profile.get("low_income_programs_supported", [])
    valid_programs = [p for p in programs if p.get("program")]
    if valid_programs:
        parts.append("\nLow-Income Program Experience:")
        for prog in valid_programs[:5]:
            prog_str = f"  - {prog['program']}"
            if prog.get("agency"):
                prog_str += f" ({prog['agency']})"
            if prog.get("scope"):
                prog_str += f": {prog['scope'][:200]}"
            parts.append(prog_str)

    # Additional capabilities
    if profile.get("residential_energy_program_experience"):
        parts.append(f"\nResidential Energy Experience: {profile['residential_energy_program_experience']}")
    if profile.get("avg_work_order_turnaround_days"):
        parts.append(f"Average Turnaround: {profile['avg_work_order_turnaround_days']} days")

    if not parts:
        return "No company profile information available. User should complete their company profile for better assistance."

    return "\n".join(parts)


def _find_relevant_chunks(raw_text: str, question: str, max_chunks: int = 3) -> str:
    """Simple keyword-based chunk retrieval for large documents."""
    if not raw_text or len(raw_text) < 10000:
        return raw_text  # Small enough to use as-is

    # Split into ~2000 char chunks with overlap
    chunk_size = 2000
    overlap = 200
    chunks: List[str] = []
    for i in range(0, len(raw_text), chunk_size - overlap):
        chunks.append(raw_text[i : i + chunk_size])

    # Score chunks by keyword matches
    question_words = set(question.lower().split())
    scored_chunks = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(1 for word in question_words if word in chunk_lower and len(word) > 3)
        scored_chunks.append((score, chunk))

    # Return top chunks
    scored_chunks.sort(reverse=True, key=lambda x: x[0])
    relevant = [chunk for score, chunk in scored_chunks[:max_chunks] if score > 0]

    if relevant:
        return "\n\n---\n\n".join(relevant)
    else:
        # No keyword matches, return beginning of document
        return raw_text[:MAX_CONTEXT_CHARS]
