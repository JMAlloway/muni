# app/ai/categorizer.py

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from app.ai.taxonomy import (
    BASE_CATEGORIES,
    fast_category_from_title,
    normalize_category_name,
)

logger = logging.getLogger(__name__)

# try to use your local LLM client if present
try:
    # adjust import to whatever you called it
    from app.ai.client import ask_llm  # type: ignore
except Exception:
    ask_llm = None


def _text_blob(title: str, description: Optional[str]) -> str:
    parts = [title or ""]
    if description:
        parts.append(description)
    return " ".join(parts).lower()


def _find_likely_categories(text: str, max_candidates: int = 6) -> List[str]:
    hits: List[tuple[str, int]] = []
    for cat_name, keywords in BASE_CATEGORIES.items():
        score = 0
        for kw in keywords:
            if kw and kw.lower() in text:
                score += 1
        if score > 0:
            hits.append((cat_name, score))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [h[0] for h in hits[:max_candidates]]


LLM_PROMPT = """You classify LOCAL GOVERNMENT procurement (city, county, transit, airport, solid waste, school).

Pick EXACTLY ONE category from this list:
{categories}

Opportunity:
Title: {title}
Description: {description}

Respond with ONLY JSON:
{{
  "category": "Construction",
  "confidence": 0.90,
  "reason": "short explanation"
}}
"""


def _call_llm(title: str, description: str, candidates: List[str]) -> Optional[Dict]:
    if not ask_llm:
        return None

    prompt = LLM_PROMPT.format(
        categories="\n".join(f"- {c}" for c in candidates),
        title=title.strip(),
        description=(description or "").strip()[:1600],
    )

    try:
        raw = ask_llm(prompt)
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return None

    if not raw:
        return None

    # strip preamble
    first = raw.find("{")
    if first > 0:
        raw = raw[first:]

    try:
        data = json.loads(raw)
        return data
    except Exception:
        # soft match: try to see if it mentioned any candidate
        low = raw.lower()
        for c in candidates:
            if c.lower() in low:
                return {
                    "category": c,
                    "confidence": 0.55,
                    "reason": "matched from freeform",
                }
        return None


def classify_opportunity(
    title: str,
    description: Optional[str] = None,
) -> Dict[str, object]:
    # 1) rule pass
    rule_cat = fast_category_from_title(title or "")
    if rule_cat and rule_cat != "Other / Miscellaneous":
        return {
            "category": rule_cat,
            "confidence": 0.92,
            "source": "rule",
        }

    # 2) narrow
    blob = _text_blob(title, description)
    candidates = _find_likely_categories(blob)
    if not candidates:
        candidates = [
            "Construction",
            "Information Technology",
            "Professional Services",
            "Facilities / Janitorial / Grounds",
            "Transportation / Fleet / Transit",
            "Solid Waste / Recycling / Environmental",
            "Other / Miscellaneous",
        ]

    # 3) LLM
    llm_resp = _call_llm(title, description or "", candidates)
    if llm_resp:
        cat = llm_resp.get("category") or "Other / Miscellaneous"
        conf = float(llm_resp.get("confidence") or 0.55)
        cat = normalize_category_name(cat)

        # floors / caps
        if conf < 0.55:
            conf = 0.55
        if conf > 0.99:
            conf = 0.99

        return {
            "category": cat,
            "confidence": conf,
            "source": "llm",
            "raw": llm_resp,
        }

    # 4) fallback
    return {
        "category": "Other / Miscellaneous",
        "confidence": 0.51,
        "source": "fallback",
    }
