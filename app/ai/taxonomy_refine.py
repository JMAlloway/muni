# app/ai/taxonomy_refine.py
from typing import List, Dict, Any
from .taxonomy import BASE_CATEGORIES

def suggest_new_keywords(
    title: str,
    description: str = "",
    full_text: str = "",
    llm_client=None,
) -> Dict[str, Any]:
    """
    Given an opportunity that fell into 'other' (or low confidence),
    ask the LLM to propose:
      - the most likely category
      - 3-8 keywords we should add to that category
    """
    blob = (full_text or "").strip() or (description or "").strip() or (title or "").strip()
    if not blob:
        return {}

    # no LLM → nothing to suggest
    if llm_client is None:
        return {}

    buckets_str = ", ".join(BASE_CATEGORIES.keys())

    messages = [
        {
            "role": "system",
            "content": (
                "You improve a fixed taxonomy of municipal procurement categories. "
                "Given an RFP text, you tell me which existing bucket it BEST fits, "
                "and which NEW KEYWORDS I should add to help the rule-based matcher. "
                "Return JSON with keys: bucket, new_keywords[]."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Our current buckets: {buckets_str}\n\n"
                f"Text:\n{blob[:3500]}"
            ),
        },
    ]

    try:
        raw = llm_client.chat(messages, temperature=0)
        import json
        data = json.loads(raw)
        # normalize
        bucket = (data.get("bucket") or "").strip().lower()
        new_keywords = data.get("new_keywords") or []
        if not isinstance(new_keywords, list):
            new_keywords = []
        return {
            "bucket": bucket,
            "new_keywords": [kw.strip().lower() for kw in new_keywords if kw.strip()],
        }
    except Exception as e:
        print(f"[AI taxonomy_refine] LLM error: {e}")
        return {}
