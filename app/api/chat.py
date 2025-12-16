"""
Chat API for AI Studio - allows users to ask questions about uploaded RFP documents.
Each chat is scoped to a session (one RFP = one chat history).
"""
import json
import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth_helpers import require_user_with_team
from app.core.db_core import engine
from app.ai.client import get_llm_client
from app.services.document_processor import DocumentProcessor
from app.storage import read_storage_bytes

logger = logging.getLogger("chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_CONTEXT_CHARS = 120000  # ~30k tokens of document context
MAX_HISTORY_MESSAGES = 10


class ChatRequest(BaseModel):
    session_id: int
    message: str


@router.get("/{session_id}/messages")
async def get_chat_messages(session_id: int, user=Depends(require_user_with_team)) -> List[Dict[str, Any]]:
    """Get all chat messages for a session."""
    async with engine.begin() as conn:
        # Verify user owns this session
        session = await conn.exec_driver_sql(
            """
            SELECT id FROM ai_studio_sessions
            WHERE id = :id AND (user_id = :uid OR (team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": session_id, "uid": user["id"], "team_id": user.get("team_id")}
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
            {"session_id": session_id}
        )
        return [dict(r._mapping) for r in res.fetchall()]


@router.post("/message")
async def send_chat_message(req: ChatRequest, user=Depends(require_user_with_team)) -> Dict[str, Any]:
    """Send a message and get AI response based on full RFP document content."""

    async with engine.begin() as conn:
        # 1. Get session with opportunity_id
        session = await conn.exec_driver_sql(
            """
            SELECT s.id, s.state_json, s.opportunity_id
            FROM ai_studio_sessions s
            WHERE s.id = :id AND (s.user_id = :uid OR (s.team_id = :team_id AND :team_id IS NOT NULL))
            """,
            {"id": req.session_id, "uid": user["id"], "team_id": user.get("team_id")}
        )
        row = session.first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = json.loads(row.state_json or "{}")
        opportunity_id = row.opportunity_id

        # 2. Get the actual document text - fetch from storage if needed
        document_text = await _get_document_text(conn, state, opportunity_id, user["id"])

        if not document_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No document found. Please upload and extract an RFP first."
            )

        # 3. Save user message
        await conn.exec_driver_sql(
            """
            INSERT INTO ai_chat_messages (session_id, user_id, role, content)
            VALUES (:session_id, :user_id, 'user', :content)
            """,
            {"session_id": req.session_id, "user_id": user["id"], "content": req.message}
        )

        # 4. Get chat history
        history = await conn.exec_driver_sql(
            """
            SELECT role, content FROM ai_chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at DESC LIMIT :limit
            """,
            {"session_id": req.session_id, "limit": MAX_HISTORY_MESSAGES}
        )
        chat_history = [dict(r._mapping) for r in history.fetchall()][::-1]

        # 5. Build context with full document text
        context = _prepare_context(document_text, req.message)

        # 6. Call LLM
        llm = get_llm_client()
        if not llm:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service unavailable")

        system_prompt = f"""You are an expert assistant helping users understand an RFP (Request for Proposal) document.

You have access to the FULL TEXT of the RFP document below. Use this to answer the user's questions accurately.

=== RFP DOCUMENT START ===
{context}
=== RFP DOCUMENT END ===

INSTRUCTIONS:
1. Answer questions by finding and quoting relevant sections from the document above
2. Be specific - mention section numbers, page references, or quote exact text when possible
3. If the user asks about requirements, deadlines, or qualifications, find the exact language
4. If something truly isn't in the document, say so, but first search thoroughly
5. For questions like "what are the important things to consider" - analyze the full document for key requirements, deadlines, evaluation criteria, and compliance items
6. Be helpful and thorough - these are important business documents"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)

        logger.info(f"Chat request session={req.session_id} context_len={len(context)} question={req.message[:100]}")

        response = llm.chat(messages, temperature=0.2)

        # 7. Save assistant response
        res = await conn.exec_driver_sql(
            """
            INSERT INTO ai_chat_messages (session_id, user_id, role, content)
            VALUES (:session_id, :user_id, 'assistant', :content)
            RETURNING id, created_at
            """,
            {"session_id": req.session_id, "user_id": user["id"], "content": response}
        )
        new_row = res.first()

        return {
            "id": new_row.id,
            "role": "assistant",
            "content": response,
            "created_at": str(new_row.created_at)
        }


async def _get_document_text(conn, state: Dict[str, Any], opportunity_id: str, user_id: str) -> str:
    """
    Get the full document text for the RFP.
    Priority:
    1. raw_text stored in session state (if we added it)
    2. Re-extract from the uploaded file
    """

    # Check if raw_text is in state
    extracted = state.get("extracted", {})
    if isinstance(extracted, dict):
        raw_text = extracted.get("raw_text", "")
        if raw_text and len(raw_text) > 500:
            logger.info(f"Using raw_text from session state, len={len(raw_text)}")
            return raw_text

    # Check for upload info in state
    upload = state.get("upload", {})
    upload_id = upload.get("id") if isinstance(upload, dict) else None
    storage_key = upload.get("storage_key") if isinstance(upload, dict) else None

    # Try to get the document from user_uploads
    if not storage_key and opportunity_id:
        res = await conn.exec_driver_sql(
            """
            SELECT storage_key, mime, filename
            FROM user_uploads
            WHERE opportunity_id = :oid AND user_id = :uid
            ORDER BY created_at DESC LIMIT 1
            """,
            {"oid": opportunity_id, "uid": user_id}
        )
        row = res.first()
        if row:
            storage_key = row.storage_key
            mime = row.mime
            filename = row.filename

    if not storage_key:
        logger.warning(f"No storage_key found for opportunity={opportunity_id}")
        # Fall back to extracted metadata if available
        return _build_fallback_context(extracted)

    # Read and extract text from the document
    try:
        logger.info(f"Re-extracting document text from storage_key={storage_key}")
        file_bytes = await asyncio.to_thread(read_storage_bytes, storage_key)
        if not file_bytes:
            logger.warning(f"Empty file from storage_key={storage_key}")
            return _build_fallback_context(extracted)

        processor = DocumentProcessor()
        result = processor.extract_text(file_bytes, mime if 'mime' in dir() else None, filename if 'filename' in dir() else "document")
        text = result.get("text", "")

        if text and len(text) > 100:
            logger.info(f"Successfully extracted document text, len={len(text)}")
            return text
        else:
            logger.warning(f"Extraction returned minimal text, len={len(text)}")
            return _build_fallback_context(extracted)

    except Exception as e:
        logger.error(f"Failed to extract document text: {e}")
        return _build_fallback_context(extracted)


def _build_fallback_context(extracted: Dict[str, Any]) -> str:
    """Build context from extracted metadata when raw text isn't available."""
    if not extracted:
        return ""

    # Handle nested structure
    if "extracted" in extracted and isinstance(extracted["extracted"], dict):
        extracted = extracted["extracted"]

    parts = []

    if extracted.get("title"):
        parts.append(f"TITLE: {extracted['title']}")

    if extracted.get("agency"):
        parts.append(f"AGENCY: {extracted['agency']}")

    if extracted.get("summary"):
        parts.append(f"SUMMARY:\n{extracted['summary']}")

    if extracted.get("scope_of_work"):
        parts.append(f"SCOPE OF WORK:\n{extracted['scope_of_work']}")

    if extracted.get("submission_instructions"):
        parts.append(f"SUBMISSION INSTRUCTIONS:\n{extracted['submission_instructions']}")

    if extracted.get("narrative_sections"):
        sections = extracted["narrative_sections"]
        if isinstance(sections, list) and sections:
            section_lines = ["REQUIRED NARRATIVE SECTIONS:"]
            for s in sections:
                if isinstance(s, dict):
                    name = s.get("name", "Unnamed")
                    reqs = s.get("requirements", "")
                    section_lines.append(f"- {name}: {reqs}")
                else:
                    section_lines.append(f"- {s}")
            parts.append("\n".join(section_lines))

    if extracted.get("attachments_forms"):
        forms = extracted["attachments_forms"]
        if isinstance(forms, list) and forms:
            parts.append("REQUIRED FORMS/ATTACHMENTS:\n" + "\n".join(f"- {f}" for f in forms))

    if extracted.get("deadlines"):
        deadlines = extracted["deadlines"]
        if isinstance(deadlines, list) and deadlines:
            deadline_lines = ["KEY DEADLINES:"]
            for d in deadlines:
                if isinstance(d, dict):
                    deadline_lines.append(f"- {d.get('event', 'Event')}: {d.get('date', '')} {d.get('time', '')}")
                else:
                    deadline_lines.append(f"- {d}")
            parts.append("\n".join(deadline_lines))

    if extracted.get("evaluation_criteria"):
        criteria = extracted["evaluation_criteria"]
        if isinstance(criteria, list) and criteria:
            parts.append("EVALUATION CRITERIA:\n" + "\n".join(f"- {c}" for c in criteria))

    return "\n\n".join(parts)


def _prepare_context(document_text: str, question: str) -> str:
    """Prepare document context, potentially finding relevant sections for large docs."""

    if len(document_text) <= MAX_CONTEXT_CHARS:
        return document_text

    # For large documents, try to find relevant chunks
    question_lower = question.lower()

    # Split into chunks
    chunk_size = 4000
    overlap = 500
    chunks = []
    for i in range(0, len(document_text), chunk_size - overlap):
        chunk = document_text[i:i + chunk_size]
        chunks.append((i, chunk))

    # Score chunks by relevance to question
    keywords = [w for w in question_lower.split() if len(w) > 3]
    scored = []
    for pos, chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(chunk_lower.count(kw) for kw in keywords)
        # Boost early chunks (usually contain important overview)
        if pos < 10000:
            score += 2
        scored.append((score, pos, chunk))

    # Sort by score, take top chunks
    scored.sort(reverse=True)

    # Always include beginning of document
    selected_chunks = [(0, document_text[:8000])]
    chars_used = 8000

    # Add relevant chunks
    for score, pos, chunk in scored:
        if chars_used >= MAX_CONTEXT_CHARS:
            break
        if pos >= 8000:  # Don't duplicate the beginning
            selected_chunks.append((pos, chunk))
            chars_used += len(chunk)

    # Sort by position to maintain document order
    selected_chunks.sort(key=lambda x: x[0])

    # Combine with markers
    result_parts = []
    for i, (pos, chunk) in enumerate(selected_chunks):
        if i > 0:
            result_parts.append("\n[...]\n")
        result_parts.append(chunk)

    return "".join(result_parts)
