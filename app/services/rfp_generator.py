import json
import re
import textwrap
from typing import Any, Dict, List, Sequence

from app.ai.client import get_llm_client


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


def generate_section_answer(question: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    q_text = question.get("question") or question.get("text") or ""
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
    return {
        "answer": answer,
        "sources": [doc.get("id") for doc in selected_docs if doc.get("id") is not None],
        "win_themes_used": [wt.get("id") for wt in (context.get("win_themes") or []) if wt.get("id")],
        "confidence": _calculate_confidence(answer, question),
        "word_count": len(answer.split()),
    }


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


def generate_batch_answers(
    questions: List[Dict[str, Any]],
    context: Dict[str, Any],
    batch_size: int = 4,
) -> List[Dict[str, Any]]:
    """
    Generate answers for multiple questions in fewer LLM calls. Falls back to per-question on errors.
    """
    llm = get_llm_client()
    if not llm:
        # Fall back to single generation for each question
        return [generate_section_answer(q, context) for q in questions]

    results: List[Dict[str, Any]] = []
    for i in range(0, len(questions), batch_size):
        batch = questions[i : i + batch_size]
        # For batch, we still score docs per question to keep relevance
        enriched_batch = []
        for q in batch:
            q_text = q.get("question") or q.get("text") or ""
            combined_docs = [{**d, "kind": "instruction"} for d in (context.get("instruction_docs") or [])] + (
                context.get("knowledge_docs") or []
            )
            selected_docs = _score_docs(q_text, combined_docs, limit=6)
            enriched_batch.append({**q, "_docs": selected_docs})

        prompt = _build_batch_prompt(enriched_batch, {**context, "knowledge_docs": []})
        try:
            resp = llm.chat(
                [
                    {"role": "system", "content": "Answer each question. Return JSON array."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
            )
            parsed = json.loads(resp)
            if not isinstance(parsed, list):
                raise ValueError("Batch response not a list")
        except Exception:
            # On failure, fall back to individual generation for this batch
            for qb in enriched_batch:
                results.append(generate_section_answer({k: v for k, v in qb.items() if not k.startswith("_")}, context))
            continue

        for idx, item in enumerate(parsed):
            q_orig = enriched_batch[idx] if idx < len(enriched_batch) else batch[idx]
            answer_text = item.get("answer") if isinstance(item, dict) else ""
            question_id = item.get("question_id") if isinstance(item, dict) else q_orig.get("id")
            wc = len((answer_text or "").split())
            selected_docs = q_orig.get("_docs") or []
            results.append(
                {
                    "id": question_id or q_orig.get("id"),
                    "question": q_orig.get("question") or q_orig.get("text"),
                    "answer": answer_text or "",
                    "sources": [d.get("id") for d in selected_docs if d.get("id") is not None],
                    "win_themes_used": [wt.get("id") for wt in (context.get("win_themes") or []) if wt.get("id")],
                    "confidence": _calculate_confidence(answer_text or "", q_orig),
                    "word_count": item.get("word_count") or wc,
                }
            )
    return results
