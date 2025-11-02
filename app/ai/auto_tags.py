# app/ai/auto_tags.py
from typing import List, Dict, Any, Optional
from .taxonomy import BASE_CATEGORIES
import json
import re

# simple keyword → tag mapping (expand as you see real data)
_DEFAULT_EXTRA_TAGS = {
    "ev charging": "ev_charging",
    "electric vehicle": "ev_charging",
    "stormwater": "stormwater",
    "janitorial": "janitorial",
    "roof": "roofing",
    "roofing": "roofing",
    "hvac": "hvac",
    "bus rapid transit": "transit",
    "brt": "transit",
    "rfp": "rfp",
    "rfq": "rfq",
    "cng": "cng_powered",
}


def _rule_tags_from_text(text: str) -> List[str]:
    text_l = (text or "").lower()
    tags: List[str] = []

    # from taxonomy: if text contains keywords of a category, add that category
    for cat, kws in BASE_CATEGORIES.items():
        for kw in kws:
            if kw in text_l:
                tags.append(cat)
                break  # don't add same category multiple times

    # from extra tag map
    for kw, tag in _DEFAULT_EXTRA_TAGS.items():
        if kw in text_l:
            tags.append(tag)

    # dedupe but keep order
    seen = set()
    clean = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            clean.append(t)
    return clean


def _strip_code_fences(s: str) -> str:
    """
    Handle outputs like:
    ```json
    ["a","b"]
    ```
    or
    ``` 
    ["a","b"]
    ```
    """
    if not s:
        return s

    s = s.strip()

    # remove leading/trailing ```...```
    if s.startswith("```"):
        # drop first line
        s = s.lstrip("`")
        # sometimes it's ```json or ```JSON
        s = re.sub(r"^(json|JSON)\s*", "", s)
    # remove trailing ```
    s = s.replace("```", "").strip()
    return s


def _normalize_tag(t: str) -> str:
    t = t.strip().strip('"').strip("'")
    t = t.lower()
    # replace spaces / dashes with underscore
    t = re.sub(r"[ \-]+", "_", t)
    return t


def _llm_tags_to_list(raw: str) -> List[str]:
    """
    Take whatever Ollama/OpenAI gave us and try really hard to make a list of strings.
    """
    if not raw:
        return []

    raw = _strip_code_fences(raw)

    # try JSON first
    if raw.startswith("[") and raw.endswith("]"):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [_normalize_tag(x) for x in data if isinstance(x, str) and x.strip()]
        except Exception:
            pass

    # some models return: construction, roadway, paving
    parts = [p for p in re.split(r"[,\n]", raw) if p.strip()]
    parts = [_normalize_tag(p) for p in parts]
    return parts


def auto_tags_from_blob(
    title: str = "",
    description: str = "",
    full_text: str = "",
    llm_client=None,
    max_tags: int = 6,
) -> List[str]:
    """
    Generate suggested tags for an opportunity.
    """
    blob = (full_text or "").strip() or (description or "").strip() or (title or "").strip()
    if not blob:
        return []

    # rule-based first
    base_tags = _rule_tags_from_text(blob)

    # no LLM? return the rule-based slice
    if llm_client is None:
        return base_tags[:max_tags]

    # LLM enhancement
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract 3-6 SHORT tags from municipal RFP/RFQ texts. "
                    "Return ONLY a JSON array of strings, all lowercase, snake_case if multiword. "
                    "Examples: [\"construction\", \"roadway\", \"stormwater\"]"
                ),
            },
            {
                "role": "user",
                "content": blob[:3500],
            },
        ]
        raw = llm_client.chat(messages, temperature=0)
        llm_tags = _llm_tags_to_list(raw)

        # merge rule-based and llm
        merged = base_tags + llm_tags
    except Exception as e:
        print(f"[AI auto_tags] LLM error: {e}")
        merged = base_tags

    # final cleanup / dedupe / filter junk
    seen = set()
    final: List[str] = []
    for t in merged:
        if not t:
            continue
        if t.startswith("```"):  # extra safety
            continue
        if t in ("json", "data", "text"):
            continue

        # --- NEW: normalize LLM typos / variants ---
        if t in ("cnv_powered", "cng_power", "cng_powerd"):
            t = "cng_powered"

        if t not in seen:
            seen.add(t)
            final.append(t)

    return final[:max_tags]

