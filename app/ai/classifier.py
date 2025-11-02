# app/ai/classifier.py
from typing import Optional, Tuple, List
import re

# pull in your beefed-up taxonomy
try:
    from app.ai.taxonomy import BASE_CATEGORIES
except ImportError:
    from taxonomy import BASE_CATEGORIES


# ------------------------------------------------------------
# Normalization helpers
# ------------------------------------------------------------

# common muni / procurement spellings we want to standardize
_NORMALIZATIONS = {
    "cm-at-risk": "cmar",
    "cm at risk": "cmar",
    "construction manager-at-risk": "cmar",
    "construction manager at risk": "cmar",
    "cma r": "cmar",
    "cma-r": "cmar",
    # transit
    "brt": "bus rapid transit",
    # noise
    "rfq": "rfq",
    "rfp": "rfp",
}


def _normalize_text(s: str) -> str:
    s = (s or "").lower()
    for bad, good in _NORMALIZATIONS.items():
        s = s.replace(bad, good)
    return s


# ------------------------------------------------------------
# Scoring helpers
# ------------------------------------------------------------

def _contains_word(text: str, word: str) -> bool:
    # match whole-ish words so "roof" doesn't match "bedproof"
    pattern = r"(?:^|[^a-z0-9])" + re.escape(word) + r"(?:$|[^a-z0-9])"
    return re.search(pattern, text) is not None


def _score_text_against_category(text: str, keywords: List[str]) -> float:
    if not text:
        return 0.0
    score = 0
    for kw in keywords:
        if _contains_word(text, kw.lower()):
            score += 1
    if score == 0:
        return 0.0
    # 1 hit → ~0.33, 2–3 hits → cap at 1.0
    return min(1.0, score / 3)


# ------------------------------------------------------------
# Main entry
# ------------------------------------------------------------

def classify_opportunity(
    title: str,
    agency: Optional[str] = None,
    description: Optional[str] = None,
    llm_client=None,
) -> Tuple[str, float]:
    """
    Classify a municipal RFP/RFQ/bid into our fixed buckets.

    Strategy:
      1. normalize text (cm-at-risk → cmar, brt → bus rapid transit)
      2. score title only
      3. score title+description
      4. if still weak AND we have an LLM → ask LLM
      5. else return best rule-based
    """
    # 1) normalize
    title = _normalize_text((title or "").strip())
    agency = _normalize_text((agency or "").strip())
    description = _normalize_text((description or "").strip())

    # 2) title-only pass
    best_cat = "other"
    best_conf = 0.0
    for cat, kws in BASE_CATEGORIES.items():
        conf = _score_text_against_category(title, kws)
        if conf > best_conf:
            best_cat = cat
            best_conf = conf

    if best_conf >= 0.7:
        return best_cat, best_conf

    # 3) title + description pass
    merged = f"{title} {description}".strip()
    for cat, kws in BASE_CATEGORIES.items():
        conf = _score_text_against_category(merged, kws)
        if conf > best_conf:
            best_cat = cat
            best_conf = conf

    if best_conf >= 0.7:
        return best_cat, best_conf

    # 4) LLM fallback
    if llm_client is None:
        # keep this loud while we tune
        print(f"[AI classifier] llm_client is None -> keeping rule result {best_cat} {best_conf}")
        return best_cat, best_conf

    try:
        buckets_str = ", ".join(BASE_CATEGORIES.keys())
        user_prompt = (
            "Classify the following municipal opportunity into exactly ONE of these buckets:\n"
            f"{buckets_str}\n"
            "Return ONLY the bucket name, nothing else.\n\n"
            f"TEXT:\n{merged[:4000]}"
        )

        # our local Ollama client exposes .chat(...)
        if hasattr(llm_client, "chat") and callable(getattr(llm_client, "chat")) and not hasattr(llm_client, "chat_completions"):
            resp_text = llm_client.chat(
                [
                    {
                        "role": "system",
                        "content": "You classify municipal RFPs into fixed buckets. Reply with just the bucket.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            llm_cat = (resp_text or "").strip().lower()
        else:
            # OpenAI style
            resp = llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You classify municipal RFPs into fixed buckets. Reply with just the bucket.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=8,
                temperature=0,
            )
            llm_cat = resp.choices[0].message.content.strip().lower()

        # tidy up
        llm_cat = llm_cat.replace(".", "").strip()

        if llm_cat in BASE_CATEGORIES:
            print(f"[AI classifier] LLM picked {llm_cat}")
            return llm_cat, 0.9

        # sometimes LLM says "construction project" or "it/software"
        for cat in BASE_CATEGORIES:
            if cat in llm_cat:
                print(f"[AI classifier] LLM fuzzy -> {cat}")
                return cat, 0.85

    except Exception as e:
        print(f"[AI classifier] LLM error: {e}")

    # 5) fallback to rule-based
    return best_cat, best_conf
