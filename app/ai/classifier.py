# app/ai/classifier.py
from typing import Optional, Tuple, List
import re

# word-boundary-ish helper
def _contains_word(text: str, word: str) -> bool:
    """
    Return True if `word` appears in `text` as a distinct token-ish unit.
    This prevents 'columbus' from matching 'bus'.
    """
    pattern = r"(?:^|[^a-z0-9])" + re.escape(word) + r"(?:$|[^a-z0-9])"
    return re.search(pattern, text) is not None


BASE_CATEGORIES = {
    "construction": [
        "construction", "roof", "roofing", "hvac", "paving", "asphalt",
        "waterline", "sewer", "wastewater", "building renovation",
        "parking lot", "concrete", "sidewalk"
    ],
    "it": [
        "software", "it", "network", "website", "web site",
        "cyber", "security", "portal", "saas"
    ],
    "professional_services": [
        "consultant", "consulting", "engineering", "architectural",
        "planning", "design services", "ae services", "a/e"
    ],
    "facilities_janitorial": [
        "janitorial", "cleaning", "custodial", "landscaping",
        "mowing", "grounds", "snow removal"
    ],
    "transportation": [
        # !!! keep these, but now we match as real words
        "transit", "bus", "fleet", "vehicle", "paratransit"
        # (no "cota" here unless you need it)
    ],
    "parks_grounds": [
        "park", "playground", "trail", "greenway", "metro parks"
    ],
    "finance_admin": [
        "audit", "insurance", "benefits", "payroll", "actuarial"
    ],
    "other": []
}


def _score_text_against_category(text: str, keywords: List[str]) -> float:
    """
    Score text for a single category.
    """
    if not text:
        return 0.0
    text_l = text.lower()
    score = 0
    for kw in keywords:
        kw_l = kw.lower()
        # use word-ish match so "columbus" doesn't match "bus"
        if _contains_word(text_l, kw_l):
            score += 1
    # normalize a little
    if score == 0:
        return 0.0
    return min(1.0, score / 3)


def classify_opportunity(
    title: str,
    agency: Optional[str] = None,
    description: Optional[str] = None,
    llm_client=None,
) -> Tuple[str, float]:
    """
    Title-first classifier.

    1. Try to classify using ONLY the title.
    2. If low confidence and we have description, add it.
    3. If still low and we have LLM, let LLM refine.
    """
    title = (title or "").strip()
    agency = (agency or "").strip()
    description = (description or "").strip()

    # ---- 1) title-only pass -----------------------------------------------
    best_cat = "other"
    best_conf = 0.0
    for cat, kws in BASE_CATEGORIES.items():
        conf = _score_text_against_category(title, kws)
        if conf > best_conf:
            best_cat = cat
            best_conf = conf

    # if we got a decent hit from the title, we're done
    if best_conf >= 0.7:
        return best_cat, best_conf

    # ---- 2) title + description (but NOT agency, to avoid "Columbus" -> "bus")
    merged = title
    if description:
        merged = f"{title} {description}"

    for cat, kws in BASE_CATEGORIES.items():
        conf = _score_text_against_category(merged, kws)
        if conf > best_conf:
            best_cat = cat
            best_conf = conf

    if best_conf >= 0.7 or llm_client is None:
        return best_cat, best_conf

        # ---- 3) LLM refinement (optional) -------------------------------------
    if llm_client is not None:
        try:
            prompt = f"""
You are classifying municipal RFPs into one of these buckets:
{list(BASE_CATEGORIES.keys())}

Return ONLY the category name.

Text:
\"\"\"{merged[:4000]}\"\"\"
"""
            # OpenAI-style
            if hasattr(llm_client, "chat") and callable(getattr(llm_client, "chat")) and not hasattr(llm_client, "chat_completions"):
                # our OllamaClient
                content = llm_client.chat(
                    [
                        {"role": "system", "content": "You label municipal RFPs into fixed buckets."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                )
                llm_cat = content.strip().lower()
            else:
                # OpenAI python client
                resp = llm_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8,
                    temperature=0,
                )
                llm_cat = resp.choices[0].message.content.strip().lower()

            if llm_cat in BASE_CATEGORIES:
                return llm_cat, 0.9
        except Exception:
            pass


    return best_cat, best_conf
