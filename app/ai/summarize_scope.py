# app/ai/summarize_scope.py
from typing import Optional

def summarize_scope(
    title: str = "",
    description: str = "",
    full_text: str = "",
    llm_client=None,
    max_words: int = 90,
) -> str:
    """
    Create a short, user-facing summary of the opportunity.
    Tries to use LLM; falls back to simple truncation.
    """
    # prefer the longest text we have
    blob = (full_text or "").strip() or (description or "").strip() or (title or "").strip()
    if not blob:
        return ""

    # cheap fallback – no LLM available
    if llm_client is None:
        # just return first N words
        words = blob.split()
        return " ".join(words[:max_words])

    try:
        # Ollama-style: we already had a .chat(...) pattern in app/ai/client.py
        messages = [
            {
                "role": "system",
                "content": (
                    "You write concise procurement summaries for municipal bids. "
                    "Use plain language. Include purpose, what is being procured, "
                    "and any dates IF stated. 3–5 sentences max."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Title: {title}\n\n"
                    f"Text:\n{blob[:4000]}\n\n"
                    "Write a concise summary:"
                ),
            },
        ]
        summary = llm_client.chat(messages, temperature=0)
        return summary.strip()
    except Exception as e:
        print(f"[AI summarize_scope] LLM error: {e}")
        words = blob.split()
        return " ".join(words[:max_words])
