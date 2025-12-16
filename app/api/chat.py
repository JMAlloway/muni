import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth_helpers import require_user_with_team
from app.core.db_core import engine
from app.ai.client import get_llm_client

router = APIRouter(prefix="/api/chat", tags=["chat"])

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
        extracted = state.get("extracted", {})
        if isinstance(extracted, dict) and "extracted" in extracted:
            # Handle nested structure
            raw_text = extracted.get("raw_text", "")
            extracted_data = extracted.get("extracted", {})
        else:
            raw_text = ""
            extracted_data = extracted

        # Build context from raw text (primary) + extracted metadata (secondary)
        if raw_text and len(raw_text) > MAX_CONTEXT_CHARS:
            # Large document - find relevant chunks
            relevant_text = _find_relevant_chunks(raw_text, req.message)
            document_context = _build_document_context(relevant_text, extracted_data)
        else:
            document_context = _build_document_context(raw_text, extracted_data)

        # 5. Call LLM
        llm = get_llm_client()
        if not llm:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service unavailable")

        system_prompt = f"""You are a helpful assistant that answers questions about an RFP (Request for Proposal) document.

IMPORTANT: Base your answers on the actual document content provided below. Be specific and quote relevant sections when possible.

--- START OF RFP DOCUMENT ---
{document_context}
--- END OF RFP DOCUMENT ---

Instructions:
- Answer questions by finding relevant information in the document above
- If you find the answer, quote or reference the specific section
- If the information is not in the document, say "I couldn't find that information in the RFP document"
- Be concise but thorough"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)

        response = llm.chat(messages, temperature=0.2)

        # 6. Save assistant response
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
