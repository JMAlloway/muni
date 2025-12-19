import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth_helpers import get_company_profile_cached, require_user_with_team
from app.core.db_core import engine
from app.ai.client import get_llm_client
from app.services.document_processor import DocumentProcessor
from app.storage import read_storage_bytes

async def _get_knowledge_context(conn, user_id: str, team_id: str = None, max_chars: int = 30000) -> str:
    """Fetch extracted text from knowledge base documents."""
    query = """
        SELECT filename, doc_type, extracted_text
        FROM knowledge_documents
        WHERE (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
          AND extraction_status = 'completed'
          AND extracted_text IS NOT NULL
          AND LENGTH(extracted_text) > 100
        ORDER BY updated_at DESC
        LIMIT 10
    """
    res = await conn.exec_driver_sql(query, {"uid": user_id, "team_id": team_id})
    rows = res.fetchall()

    if not rows:
        return ""

    parts = ["=== KNOWLEDGE BASE DOCUMENTS ==="]
    total_chars = 0

    for row in rows:
        m = row._mapping
        filename = m.get("filename", "Document")
        doc_type = m.get("doc_type", "other")
        text = m.get("extracted_text", "")

        if total_chars + len(text) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 500:
                text = text[:remaining] + "\n[... truncated ...]"
            else:
                break

        parts.append(f"\n--- {filename} ({doc_type}) ---\n{text}")
        total_chars += len(text)

    return "\n".join(parts)

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# Token/character limits
# Keep under provider TPM limits (~30k tokens ≈ 120k chars) to avoid rate_limit_exceeded
MAX_CONTEXT_CHARS = 120000
MAX_HISTORY_MESSAGES = 10
_profile_doc_cache: Dict[str, str] = {}
PROFILE_DOC_FIELDS: List[tuple[str, str]] = [
    ("capability_statement", "Capability Statement"),
    ("insurance_certificate", "Certificate of Insurance"),
    ("w9_upload", "W-9 Form"),
    ("business_license", "Business License"),
    ("bonding_letter", "Bonding Letter"),
    ("ohio_certificate", "Ohio Certificate"),
    ("cert_upload", "Certification Documents"),
    ("financial_statements", "Financial Statements"),
    ("org_chart", "Organizational Chart"),
    ("digital_signature", "Digital Signature"),
    ("signature_image", "Signature Image"),
    ("previous_contracts", "Previous Contracts"),
    ("product_catalogs", "Product Catalogs"),
    ("price_list_upload", "Price List"),
    ("safety_sheets", "Safety Data Sheets"),
    ("warranty_info", "Warranty Information"),
    ("debarment_certification", "Debarment Certification"),
    ("labor_compliance_cert", "Labor Compliance Certificate"),
    ("conflict_of_interest", "Conflict of Interest Disclosure"),
    ("emr_certificate", "EMR Certificate"),
    ("drug_free_policy", "Drug Free Policy"),
    ("bank_reference_letter", "Bank Reference Letter"),
    ("quality_cert", "Quality Certification"),
    ("ref1_letter", "Reference Letter 1"),
    ("ref2_letter", "Reference Letter 2"),
    ("ref3_letter", "Reference Letter 3"),
    ("ref4_letter", "Reference Letter 4"),
    ("ref5_letter", "Reference Letter 5"),
]


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
        raw_text_state, extracted_data = _resolve_extracted_state(extracted_state)
        document_text = await _get_document_text(conn, state if isinstance(state, dict) else {}, row.opportunity_id, user["id"])
        fallback_context = _build_fallback_context(extracted_state)

        if document_text == fallback_context:
            # No raw text available; fallback already formatted
            document_context = fallback_context
        else:
            raw_text = document_text or raw_text_state
            prepared_text = _prepare_context(raw_text or "", req.message)
            document_context = _build_document_context(prepared_text, extracted_data)

        # 5. Load company profile context
        company_profile = await get_company_profile_cached(conn, user["id"], user.get("team_id"))
        profile_docs = await _extract_profile_documents(company_profile)
        company_context = _format_company_profile(company_profile, profile_docs)

        # 5b. Load knowledge base documents
        knowledge_context = await _get_knowledge_context(conn, user["id"], user.get("team_id"))

        # 6. Call LLM
        llm = get_llm_client()
        if not llm:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service unavailable")

        system_prompt = f"""You are an expert assistant helping a company respond to an RFP (Request for Proposal).

You have access to:
1. The FULL TEXT of the RFP document
2. The user's COMPANY PROFILE with their qualifications, experience, and capabilities
3. Supporting documents from the company's knowledge base

=== COMPANY PROFILE START ===
{company_context}
=== COMPANY PROFILE END ===

=== RFP DOCUMENT START ===
{document_context}
=== RFP DOCUMENT END ===

{knowledge_context if knowledge_context else ""}

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


def _prepare_context(document_text: str, question: str) -> str:
    """
    Prepare document context with improved section detection.
    Preserves document structure while prioritizing relevant sections.
    """
    if not document_text:
        return ""

    # If document fits, use it all
    if len(document_text) <= MAX_CONTEXT_CHARS:
        return document_text

    # Split by section headers (common RFP patterns)
    section_pattern = r"\n(?=[A-Z][A-Z\s]{0,30}:|\d+\.\s+[A-Z]|SECTION\s+\d|ARTICLE\s+\d|PART\s+\d)"
    sections = re.split(section_pattern, document_text)

    # If no sections found, fall back to chunk-based approach
    if len(sections) <= 1:
        return _chunk_based_context(document_text, question)

    # Score sections by relevance
    question_lower = question.lower()
    keywords = [w for w in question_lower.split() if len(w) > 3]

    # Add domain-specific keywords based on question type
    if any(w in question_lower for w in ["insurance", "liability", "coverage"]):
        keywords.extend(["insurance", "liability", "coverage", "certificate", "indemnification"])
    if any(w in question_lower for w in ["deadline", "due", "submit", "when"]):
        keywords.extend(["deadline", "due", "submission", "date", "calendar"])
    if any(w in question_lower for w in ["qualify", "requirement", "eligible"]):
        keywords.extend(["requirement", "qualification", "mandatory", "must", "shall"])
    if any(w in question_lower for w in ["experience", "past", "reference"]):
        keywords.extend(["experience", "reference", "project", "performance", "similar"])

    scored_sections = []
    for i, section in enumerate(sections):
        section_lower = section.lower()
        score = sum(section_lower.count(kw) for kw in keywords)

        # Boost first section (usually contains overview)
        if i == 0:
            score += 5

        # Boost sections with headers matching keywords
        first_line = section.split("\n")[0][:100].lower()
        header_boost = sum(2 for kw in keywords if kw in first_line)
        score += header_boost

        scored_sections.append((score, i, section))

    # Sort by score, keep top sections
    scored_sections.sort(reverse=True, key=lambda x: x[0])

    # Always include first section + top relevant sections
    selected = []
    selected_indices = set()
    chars_used = 0

    # Add first section (overview)
    if sections[0]:
        selected.append((0, sections[0]))
        selected_indices.add(0)
        chars_used += len(sections[0])

    # Add high-scoring sections
    for score, idx, section in scored_sections:
        if idx in selected_indices:
            continue
        if chars_used + len(section) > MAX_CONTEXT_CHARS:
            break
        selected.append((idx, section))
        selected_indices.add(idx)
        chars_used += len(section)

    # Sort by original order to maintain document flow
    selected.sort(key=lambda x: x[0])

    # Combine with markers
    result_parts = []
    prev_idx = -1
    for idx, section in selected:
        if prev_idx >= 0 and idx > prev_idx + 1:
            result_parts.append("\n\n[...section omitted...]\n\n")
        result_parts.append(section)
        prev_idx = idx

    return "".join(result_parts)


def _chunk_based_context(document_text: str, question: str) -> str:
    """Fallback chunk-based context for documents without clear sections."""
    chunk_size = 4000
    overlap = 500
    chunks = []

    for i in range(0, len(document_text), chunk_size - overlap):
        chunk = document_text[i : i + chunk_size]
        chunks.append((i, chunk))

    question_lower = question.lower()
    keywords = [w for w in question_lower.split() if len(w) > 3]

    scored = []
    for pos, chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(chunk_lower.count(kw) for kw in keywords)
        if pos < 10000:
            score += 2  # Boost beginning
        scored.append((score, pos, chunk))

    scored.sort(reverse=True)

    # Build context
    selected = [(0, document_text[:8000])]  # Always include beginning
    chars_used = 8000

    for score, pos, chunk in scored:
        if chars_used >= MAX_CONTEXT_CHARS:
            break
        if pos >= 8000:
            selected.append((pos, chunk))
            chars_used += len(chunk)

    selected.sort(key=lambda x: x[0])

    result_parts = []
    for i, (pos, chunk) in enumerate(selected):
        if i > 0:
            result_parts.append("\n[...]\n")
        result_parts.append(chunk)

    return "".join(result_parts)

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


def _build_fallback_context(extracted_state: Dict[str, Any]) -> str:
    """Build a minimal context from extracted metadata when raw text is unavailable."""
    _, extracted_data = _resolve_extracted_state(extracted_state)
    return _build_document_context("", extracted_data)


async def _get_document_text(conn, state: Dict[str, Any], opportunity_id: str, user_id: str) -> str:
    """
    Get the full document text for the RFP.
    Priority:
    1. raw_text stored in session state (fast - no I/O)
    2. Re-extract from uploaded file (slow - only if raw_text missing)
    """

    extracted = state.get("extracted", {}) if isinstance(state, dict) else {}

    # 1. FIRST: Check session state for cached raw_text
    if isinstance(extracted, dict):
        raw_text = extracted.get("raw_text", "")
        if raw_text and len(raw_text) > 500:
            logger.info(f"Using cached raw_text from session state, len={len(raw_text)}")
            return raw_text

    # 2. SECOND: Check nested structure (some sessions have double nesting)
    nested_extracted = extracted.get("extracted", {}) if isinstance(extracted, dict) else {}
    if isinstance(nested_extracted, dict):
        raw_text = nested_extracted.get("raw_text", "")
        if raw_text and len(raw_text) > 500:
            logger.info(f"Using cached raw_text from nested state, len={len(raw_text)}")
            return raw_text

    # 3. FALLBACK: Re-extract from storage (expensive - avoid if possible)
    logger.warning("No cached raw_text found, falling back to storage extraction")

    upload = state.get("upload", {}) if isinstance(state, dict) else {}
    storage_key = upload.get("storage_key") if isinstance(upload, dict) else None
    mime = upload.get("mime") if isinstance(upload, dict) else None
    filename = upload.get("filename") if isinstance(upload, dict) else "document"

    # Try to get from user_uploads if not in state
    if not storage_key and opportunity_id:
        res = await conn.exec_driver_sql(
            """
            SELECT storage_key, mime, filename
            FROM user_uploads
            WHERE opportunity_id = :oid AND user_id = :uid
            ORDER BY created_at DESC LIMIT 1
            """,
            {"oid": opportunity_id, "uid": user_id},
        )
        row = res.first()
        if row:
            mapping = row._mapping if hasattr(row, "_mapping") else {}
            storage_key = mapping.get("storage_key") or getattr(row, "storage_key", None)
            mime = mapping.get("mime") or getattr(row, "mime", None)
            filename = mapping.get("filename") or getattr(row, "filename", filename)

    if not storage_key:
        logger.warning(f"No storage_key found for opportunity={opportunity_id}")
        return _build_fallback_context(extracted)

    # Read and extract from storage
    try:
        logger.info(f"Re-extracting document from storage_key={storage_key}")
        file_bytes = await asyncio.to_thread(read_storage_bytes, storage_key)
        if not file_bytes:
            return _build_fallback_context(extracted)

        processor = DocumentProcessor()
        result = processor.extract_text(file_bytes, mime, filename)
        text = result.get("text", "")

        if text and len(text) > 100:
            logger.info(f"Extracted document text from storage, len={len(text)}")
            return text

    except Exception as e:
        logger.error(f"Failed to extract document: {e}")

    return _build_fallback_context(extracted)

def _truncate_text(text: str, max_chars: int = 2000) -> str:
    if not text:
        return ""
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


async def _extract_profile_documents(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Pull text from company profile file attachments (capability statement, insurance, W-9, etc.)
    so the chat model can reference them.
    """
    results: List[Dict[str, str]] = []
    processor = DocumentProcessor()

    for field, label in PROFILE_DOC_FIELDS:
        inline_text = profile.get(f"{field}_text")
        inline_name = profile.get(f"{field}_name") or label
        storage_key = profile.get(field)
        has_storage = bool(storage_key) and isinstance(storage_key, str) and "UploadFile(" not in storage_key and "Headers(" not in storage_key

        if inline_text:
            clipped = _truncate_text(str(inline_text), 2000)
            if has_storage:
                _profile_doc_cache[storage_key] = clipped
            results.append({"name": inline_name, "text": clipped})
            continue

        if not has_storage:
            continue

        cached = _profile_doc_cache.get(storage_key)
        if cached:
            results.append({"name": inline_name, "text": cached})
            continue

        try:
            file_bytes = await asyncio.to_thread(read_storage_bytes, storage_key)
            if not file_bytes:
                continue
            filename = inline_name or field
            mime = profile.get(f"{field}_mime") or (mimetypes.guess_type(filename)[0] if filename else None)
            extracted = await asyncio.to_thread(processor.extract_text, file_bytes, mime, filename)
            text = extracted.get("text") if isinstance(extracted, dict) else ""
            if not text:
                continue
            clipped = _truncate_text(text, 2000)
            _profile_doc_cache[storage_key] = clipped
            results.append({"name": inline_name, "text": clipped})
        except Exception as exc:
            logger.warning("Could not extract profile document %s: %s", field, exc)
            continue

    return results


def _format_company_profile(profile: Dict[str, Any], doc_texts: Optional[List[Dict[str, str]]] = None) -> str:
    """Format company profile into readable context for the LLM."""
    parts = []

    # Basic company info
    if profile.get("legal_name"):
        parts.append(f"Company Name: {profile['legal_name']}")
    if profile.get("dba"):
        parts.append(f"DBA: {profile['dba']}")
    if profile.get("entity_type"):
        parts.append(f"Entity Type: {profile['entity_type']}")
    if profile.get("state_of_incorporation"):
        parts.append(f"State of Incorporation: {profile['state_of_incorporation']}")
    if profile.get("year_established"):
        parts.append(f"Year Established: {profile['year_established']}")
    if profile.get("years_experience"):
        parts.append(f"Years of Experience: {profile['years_experience']}")
    if profile.get("years_in_business"):
        parts.append(f"Years in Business: {profile['years_in_business']}")
    if profile.get("hq_address"):
        parts.append(f"Address: {profile['hq_address']}")
    if profile.get("business_address"):
        addr = profile["business_address"]
        addr_parts = [addr.get("street", ""), addr.get("city", ""), addr.get("state", ""), addr.get("zip", "")]
        addr_line = ", ".join([p for p in addr_parts if p])
        if addr_line:
            parts.append(f"Business Address: {addr_line}")
    if profile.get("phone"):
        parts.append(f"Phone: {profile['phone']}")
    if profile.get("email"):
        parts.append(f"Email: {profile['email']}")
    if profile.get("website"):
        parts.append(f"Website: {profile['website']}")
    if profile.get("service_area"):
        parts.append(f"Service Area: {profile['service_area']}")
    if profile.get("service_area_list"):
        parts.append(f"Service Areas: {', '.join([s for s in profile.get('service_area_list', []) if s])}")
    if profile.get("service_categories"):
        parts.append(f"Service Categories: {', '.join([c for c in profile.get('service_categories', []) if c])}")
    if profile.get("company_overview"):
        parts.append(f"Overview: {profile['company_overview']}")
    if profile.get("experience"):
        parts.append(f"Company Experience: {profile['experience']}")
    if profile.get("offerings"):
        parts.append(f"Services/Product Offerings: {profile['offerings']}")
    if profile.get("sole_responsibility_statement"):
        parts.append(f"Sole Responsibility Statement: {profile['sole_responsibility_statement']}")
    if profile.get("criminal_history_check_policy"):
        parts.append(f"Criminal History Check Policy: {profile['criminal_history_check_policy']}")
    if profile.get("recordkeeping_controls"):
        parts.append(f"Recordkeeping Controls: {profile['recordkeeping_controls']}")

    # Primary contact
    contact = profile.get("primary_contact", {})
    if contact.get("name"):
        contact_info = f"Primary Contact: {contact['name']}"
        if contact.get("title"):
            contact_info += f", {contact['title']}"
        if contact.get("email"):
            contact_info += f" ({contact['email']})"
        parts.append(contact_info)

    # Authorized signatory
    signer = profile.get("authorized_signatory", {})
    if signer.get("name"):
        signer_info = f"Authorized Signatory: {signer['name']}"
        if signer.get("title"):
            signer_info += f", {signer['title']}"
        if signer.get("email"):
            signer_info += f" ({signer['email']})"
        if signer.get("phone"):
            signer_info += f" [{signer['phone']}]"
        parts.append(signer_info)

    # Certifications (MBE, SBE, WBE, EDGE)
    certs = profile.get("certifications_status", {})
    active_certs = [c for c in ["MBE", "SBE", "EDGE", "WBE"] if certs.get(c)]
    if active_certs:
        parts.append(f"Certifications: {', '.join(active_certs)}")
    if certs.get("details"):
        parts.append(f"Certification Details: {certs['details']}")
    if certs.get("certifications"):
        parts.append("Other Certifications: " + ", ".join([c for c in certs.get("certifications", []) if c]))

    # Contractor licenses
    licenses = profile.get("contractor_licenses", [])
    valid_licenses = [lic for lic in licenses if lic.get("number")]
    if valid_licenses:
        lic_strs = []
        for lic in valid_licenses:
            lic_str = f"{lic.get('state', 'State')} #{lic.get('number', '')}"
            if lic.get("type"):
                lic_str = f"{lic.get('type')} - " + lic_str
            if lic.get("issuing_authority"):
                lic_str += f" ({lic.get('issuing_authority')})"
            if lic.get("expiry"):
                lic_str += f" (exp: {lic['expiry']})"
            lic_strs.append(lic_str)
        parts.append(f"Contractor Licenses: {'; '.join(lic_strs)}")

    # Insurance
    insurance = profile.get("insurance", {})
    ins_parts = []
    gl = insurance.get("general_liability", {})
    if gl.get("carrier") or gl.get("policy_number"):
        gl_limits = []
        if gl.get("per_occurrence_limit"):
            gl_limits.append(f"Per Occurrence: {gl['per_occurrence_limit']}")
        if gl.get("aggregate_limit"):
            gl_limits.append(f"Aggregate: {gl['aggregate_limit']}")
        limit_str = "; ".join(gl_limits) if gl_limits else gl.get("limit", "N/A")
        ins_parts.append(f"General Liability: {gl.get('carrier', '')} #{gl.get('policy_number', '')} ({limit_str})")
        if gl.get("effective") or gl.get("expiry"):
            ins_parts.append(f"GL Dates: {gl.get('effective', '')} - {gl.get('expiry', '')}")
    auto = insurance.get("auto_liability", {})
    if auto.get("carrier") or auto.get("policy_number"):
        ins_parts.append(
            f"Auto Liability: {auto.get('carrier', '')} #{auto.get('policy_number', '')} (Limit: {auto.get('limit', '')})"
        )
        if auto.get("effective") or auto.get("expiry"):
            ins_parts.append(f"Auto Dates: {auto.get('effective', '')} - {auto.get('expiry', '')}")
    umb = insurance.get("umbrella_excess", {})
    if umb.get("carrier") or umb.get("policy_number"):
        ins_parts.append(
            f"Umbrella/Excess: {umb.get('carrier', '')} #{umb.get('policy_number', '')} (Limit: {umb.get('limit', '')})"
        )
        if umb.get("effective") or umb.get("expiry"):
            ins_parts.append(f"Umbrella Dates: {umb.get('effective', '')} - {umb.get('expiry', '')}")
    if insurance.get("workers_comp_certificate", {}).get("id"):
        ins_parts.append("Workers Comp: Active")
    if ins_parts:
        parts.append(f"Insurance: {'; '.join(ins_parts)}")

    # Bonding
    bonding = profile.get("bonding", {})
    if bonding.get("single_project_limit") or bonding.get("aggregate_limit") or bonding.get("surety_company"):
        b_parts = []
        if bonding.get("single_project_limit"):
            b_parts.append(f"Single: {bonding['single_project_limit']}")
        if bonding.get("aggregate_limit"):
            b_parts.append(f"Aggregate: {bonding['aggregate_limit']}")
        if bonding.get("surety_company"):
            b_parts.append(f"Surety: {bonding['surety_company']}")
        if bonding.get("surety_contact"):
            b_parts.append(f"Surety Contact: {bonding['surety_contact']}")
        parts.append("Bonding: " + "; ".join(b_parts))

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
    if profile.get("avg_annual_revenue"):
        parts.append(f"Avg Annual Revenue: {profile['avg_annual_revenue']}")
    if profile.get("full_time_employees"):
        parts.append(f"Full-Time Employees: {profile['full_time_employees']}")
    if profile.get("safety_program_description"):
        parts.append(f"\nSafety Program: {profile['safety_program_description']}")
    if profile.get("emr"):
        parts.append(f"EMR: {profile['emr']}")
    if profile.get("naics_codes"):
        parts.append(f"NAICS Codes: {', '.join([c for c in profile.get('naics_codes', []) if c])}")
    if profile.get("can_meet_timeframe") is not None:
        parts.append(f"Can Meet RFP Timeframe: {'Yes' if profile['can_meet_timeframe'] else 'No'}")
    attachments = profile.get("attachments", [])
    if attachments:
        names = [a.get("name") or a.get("filename") or a.get("id") for a in attachments if isinstance(a, dict)]
        names = [n for n in names if n]
        if names:
            parts.append("Supporting Attachments: " + ", ".join(names[:10]))

    # Subcontractors
    subs = profile.get("subcontractors", [])
    valid_subs = [s for s in subs if s.get("company_name")]
    if valid_subs:
        parts.append("\nSubcontractors:")
        for sub in valid_subs[:10]:
            sub_line = f"  - {sub['company_name']}"
            if sub.get("trade"):
                sub_line += f" ({sub['trade']})"
            contact_bits = []
            if sub.get("contact_name"):
                contact_bits.append(sub["contact_name"])
            if sub.get("phone"):
                contact_bits.append(sub["phone"])
            if sub.get("email"):
                contact_bits.append(sub["email"])
            if contact_bits:
                sub_line += f" | " + ", ".join(contact_bits)
            if sub.get("license_number"):
                sub_line += f" | License: {sub['license_number']}"
            parts.append(sub_line)

    # Uploaded document contents
    doc_fields = [
        ("capability_statement_text", "Capability Statement"),
        ("insurance_certificate_text", "Insurance Certificate"),
        ("bonding_letter_text", "Bonding Letter"),
        ("w9_upload_text", "W-9 Form"),
        ("business_license_text", "Business License"),
        ("previous_contracts_text", "Previous Contracts"),
        ("org_chart_text", "Organization Chart"),
        ("financial_statements_text", "Financial Statements"),
        ("cert_upload_text", "Certifications"),
        ("ohio_certificate_text", "Ohio Certificate"),
        ("safety_sheets_text", "Safety Data Sheets"),
        ("warranty_info_text", "Warranty Information"),
        ("price_list_upload_text", "Price List"),
        ("product_catalogs_text", "Product Catalogs"),
        ("debarment_certification_text", "Debarment Certification"),
        ("labor_compliance_cert_text", "Labor Compliance Certificate"),
        ("conflict_of_interest_text", "Conflict of Interest Disclosure"),
    ]

    doc_content_parts = []
    for field_key, label in doc_fields:
        content = profile.get(field_key, "")
        if content and len(content.strip()) > 50:  # Only include meaningful content
            truncated = content[:8000] if len(content) > 8000 else content
            doc_content_parts.append(f"\n=== {label} ===\n{truncated}")

    # Include reference letters
    for i in range(1, 6):
        ref_text = profile.get(f"ref{i}_letter_text", "")
        if ref_text and len(ref_text.strip()) > 50:
            truncated = ref_text[:4000] if len(ref_text) > 4000 else ref_text
            doc_content_parts.append(f"\n=== Reference Letter {i} ===\n{truncated}")

    if doc_content_parts:
        parts.append("\n\n--- UPLOADED DOCUMENT CONTENTS ---")
        parts.extend(doc_content_parts)

    # Compliance & declarations
    compliance = profile.get("compliance", {})
    comp_flags = []
    if compliance.get("non_collusion_certified"):
        comp_flags.append("Non-collusion certified")
    if compliance.get("prevailing_wage_compliant"):
        comp_flags.append("Prevailing wage compliant")
    if compliance.get("contract_terms_agreed"):
        comp_flags.append("Contract terms agreed")
    addenda = compliance.get("addenda_acknowledged")
    if addenda:
        comp_flags.append(f"Addenda acknowledged: {', '.join([str(a) for a in addenda if a])}")
    if comp_flags:
        parts.append("Compliance: " + "; ".join(comp_flags))

    attachment_entries: List[tuple[str, str]] = []
    seen_labels = set()
    for doc in doc_texts or []:
        text_val = doc.get("text") if isinstance(doc, dict) else None
        if not text_val:
            continue
        label = doc.get("name") or "Attachment"
        attachment_entries.append((label, _truncate_text(str(text_val), 1200)))
        seen_labels.add(label.lower())
    for field, label in PROFILE_DOC_FIELDS:
        text_val = profile.get(f"{field}_text")
        if not text_val:
            continue
        display_name = profile.get(f"{field}_name") or label
        canonical = display_name.lower()
        if canonical in seen_labels or label.lower() in seen_labels:
            continue
        attachment_entries.append((display_name, _truncate_text(str(text_val), 1200)))
        seen_labels.update({canonical, label.lower()})

    if attachment_entries:
        parts.append("Company Profile Attachments:")
        for name, snippet in attachment_entries:
            parts.append(f"- {name}: {snippet}")

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
