import json
import re
import textwrap
import logging
from typing import Any, Dict, List, Sequence

from app.services.response_cache import ResponseCache

from app.ai.client import get_llm_client

logger = logging.getLogger("rfp_generator")


def _extract_keywords(question: str, min_len: int = 4) -> List[str]:
    words = re.findall(r"[A-Za-z0-9]+", question or "")
    return [w.lower() for w in words if len(w) >= min_len][:20]


def _score_docs(question: str, docs: Sequence[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    terms = _extract_keywords(question)
    scored = []
    for doc in docs:
        text = (doc.get("extracted_text") or "")[:12000].lower()
        meta = dict(doc)
        score = 0
        for t in terms:
            score += text.count(t)
        meta["score"] = score
        meta["snippet"] = textwrap.shorten(doc.get("extracted_text") or "", width=800, placeholder="...")
        scored.append(meta)
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored[:limit] if limit else scored


def _format_win_themes(win_themes: Sequence[Dict[str, Any]]) -> str:
    if not win_themes:
        return "No win themes provided."
    lines = []
    for theme in win_themes:
        title = theme.get("title") or "Theme"
        desc = theme.get("description") or ""
        metrics = theme.get("metrics") or {}
        metrics_str = ", ".join([f"{k}: {v}" for k, v in metrics.items()]) if isinstance(metrics, dict) else ""
        line = f"- {title}: {desc}"
        if metrics_str:
            line += f" (Metrics: {metrics_str})"
        lines.append(line)
    return "\n".join(lines)


def _format_documents(docs: Sequence[Dict[str, Any]]) -> str:
    if not docs:
        return "No supporting documents selected."
    out = []
    for doc in docs:
        title = doc.get("filename") or doc.get("title") or f"Doc {doc.get('id')}"
        snippet = doc.get("snippet") or textwrap.shorten(doc.get("extracted_text") or "", width=500, placeholder="...")
        prefix = "[Instruction] " if doc.get("kind") == "instruction" else "- "
        out.append(f"{prefix}{title}: {snippet}")
    return "\n".join(out)


def _format_instructions(docs: Sequence[Dict[str, Any]]) -> str:
    if not docs:
        return "No instruction documents provided."
    lines = []
    for doc in docs:
        title = doc.get("filename") or f"Doc {doc.get('id')}"
        snippet = doc.get("snippet") or textwrap.shorten(doc.get("extracted_text") or "", width=800, placeholder="...")
        lines.append(f"- {title}: {snippet}")
    return "\n".join(lines)


def _calculate_confidence(answer: str, question: Dict[str, Any]) -> float:
    wc = len((answer or "").split())
    max_words = question.get("max_words") or 0
    base = 0.55
    if max_words:
        if 0 < wc <= max_words:
            base += 0.25
        elif wc > max_words * 1.1:
            base -= 0.1
    if wc < 50:
        base -= 0.1
    return round(max(0.1, min(base, 0.95)), 2)


def build_prompt(question_text: str, context: Dict[str, Any], max_words: int | None = None) -> str:
    company_profile = context.get("company_profile") or {}
    win_themes = context.get("win_themes") or []
    docs = context.get("knowledge_docs") or []
    instruction_docs = context.get("instruction_docs") or []
    instructions = context.get("custom_instructions") or ""
    requirement = f"Maximum length: {max_words} words" if max_words else "Keep the answer concise."

    return textwrap.dedent(
        f"""
        You are an expert RFP response writer. Write a direct, evidence-backed answer.

        RFP Question:
        {question_text}

        Company Information (JSON):
        {json.dumps(company_profile, ensure_ascii=False, indent=2)}

        Win Themes to Highlight:
        {_format_win_themes(win_themes)}

        RFP Instructions / Requirements (from uploaded RFP docs):
        {_format_instructions(instruction_docs)}

        Supporting Evidence from Past Projects:
        {_format_documents(docs)}

        Custom Instructions:
        {instructions or 'None'}

        Requirements:
        - Address the question completely and stay factual.
        - Cite specific examples, metrics, and differentiators from the context.
        - {requirement}
        - Use a confident, professional tone.
        """
    ).strip()


response_cache = ResponseCache()


async def generate_section_answer(question: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an answer for a single RFP section with caching."""
    q_text = question.get("question") or question.get("text") or ""
    q_id = question.get("id", "")

    # Check cache first
    cached = await response_cache.get(q_text, context)
    if cached:
        cached["id"] = q_id
        cached["cached"] = True
        return cached

    knowledge_docs = context.get("knowledge_docs") or []
    instruction_docs = context.get("instruction_docs") or []
    # Score combined docs so instructions and knowledge both influence relevance
    combined_docs = [
        {**doc, "kind": "instruction"} for doc in instruction_docs
    ] + knowledge_docs
    selected_docs = _score_docs(q_text, combined_docs, limit=6)
    prompt = build_prompt(
        q_text,
        {**context, "knowledge_docs": selected_docs, "instruction_docs": instruction_docs},
        question.get("max_words"),
    )

    llm = get_llm_client()
    try:
        response_text = ""
        if llm:
            response_text = llm.chat(
                [
                    {"role": "system", "content": "You are an expert RFP writer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
            ) or ""
        else:
            response_text = (
                f"Draft response for: {q_text}\n\n"
                f"Key strengths: {_format_win_themes(context.get('win_themes') or [])}\n\n"
                f"References:\n{_format_documents(selected_docs)}"
            )
    except Exception as exc:  # pragma: no cover
        response_text = (
            f"Draft response for: {q_text}\n\n"
            f"(LLM unavailable: {exc})\n"
            f"References:\n{_format_documents(selected_docs)}"
        )

    answer = response_text.strip()
    result = {
        "id": q_id,
        "question": q_text,
        "answer": answer,
        "sources": [doc.get("id") for doc in selected_docs if doc.get("id") is not None],
        "win_themes_used": [wt.get("id") for wt in (context.get("win_themes") or []) if wt.get("id")],
        "confidence": _calculate_confidence(answer, question),
        "word_count": len(answer.split()),
        "cached": False,
    }

    # Cache the result
    await response_cache.set(q_text, context, result)

    return result


def _build_batch_prompt(questions: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
    company_profile = context.get("company_profile") or {}
    win_themes = _format_win_themes(context.get("win_themes") or [])
    instruction_docs = _format_instructions(context.get("instruction_docs") or [])
    knowledge_docs = _format_documents(context.get("knowledge_docs") or [])
    instructions = context.get("custom_instructions") or "None"
    q_list = "\n".join(
        [
            f"{idx+1}. ID {q.get('id')}: {q.get('question') or q.get('text') or ''} (max {q.get('max_words', 'N/A')} words)"
            for idx, q in enumerate(questions)
        ]
    )
    return textwrap.dedent(
        f"""
        You are an expert RFP response writer. Answer each question independently.

        Company Information (JSON):
        {json.dumps(company_profile, ensure_ascii=False, indent=2)}

        Win Themes to Highlight:
        {win_themes}

        RFP Instructions / Requirements (from uploaded RFP docs):
        {instruction_docs}

        Supporting Evidence from Past Projects:
        {knowledge_docs}

        Custom Instructions:
        {instructions}

        Questions:
        {q_list}

        Return JSON array in the same order:
        [{{"question_id": "...", "answer": "...", "word_count": N}}]
        """
    ).strip()


async def generate_batch_answers(
    questions: List[Dict[str, Any]],
    context: Dict[str, Any],
    batch_size: int = 4,
) -> List[Dict[str, Any]]:
    """Generate answers in batches with smart fallback."""
    llm = get_llm_client()
    if not llm:
        return [await generate_section_answer(q, context) for q in questions]

    results: List[Dict[str, Any]] = []

    for i in range(0, len(questions), batch_size):
        batch = questions[i : i + batch_size]

        # Try batch generation
        try:
            batch_result = _generate_batch(llm, batch, context)
            if batch_result:
                results.extend(batch_result)
                continue
        except Exception as e:
            logger.warning(f"Batch generation failed: {e}")

        # Smart fallback: retry batch ONCE before individual
        try:
            logger.info("Retrying batch generation...")
            batch_result = _generate_batch(llm, batch, context)
            if batch_result:
                results.extend(batch_result)
                continue
        except Exception:
            pass

        # Final fallback: individual generation for THIS batch only
        logger.warning(f"Falling back to individual generation for {len(batch)} sections")
        for section in batch:
            try:
                result = await generate_section_answer(section, context)
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "id": section.get("id"),
                        "answer": "",
                        "error": str(e),
                    }
                )

    return results
