# app/ai/extract_fields.py
import re
import json
from typing import Optional, Dict, Any

# Common patterns we can extract without AI
DATE_PAT = re.compile(
    r"(?:due|closing|proposal(?:s)? due|bids? due)\s*[:\-]?\s*"
    r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

TIME_PAT = re.compile(
    r"(\d{1,2}:\d{2}\s*(?:a\.m\.|p\.m\.|am|pm)?)",
    re.IGNORECASE,
)

EMAIL_PAT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

SUBMISSION_PATTERNS = [
    "electronic bids will be received",
    "submit via",
    "submissions must be uploaded",
    "delivered to",
    "emailed to",
    "submit proposals to",
]


def _regex_extract(text: str) -> Dict[str, Any]:
    """Quick non-AI field extraction using regex."""
    data: Dict[str, Any] = {}

    if not text:
        return data

    if m := DATE_PAT.search(text):
        data["due_date_raw"] = m.group(1).strip()

    if m := TIME_PAT.search(text):
        data["due_time_raw"] = m.group(1).strip()

    if m := EMAIL_PAT.search(text):
        data["contact_email"] = m.group(0).strip()

    for pat in SUBMISSION_PATTERNS:
        if pat in text.lower():
            data["submission_hint"] = pat
            break

    return data


def extract_key_fields(
    text: Optional[str],
    llm_client=None
) -> Dict[str, Any]:
    """
    Try regex first; if missing key info and llm_client is provided,
    use LLM (Ollama or OpenAI) to extract structured fields.
    """
    if not text:
        return {}

    data = _regex_extract(text)

    # If regex already found good stuff, skip LLM
    if ("due_date_raw" in data) and ("contact_email" in data or "submission_hint" in data):
        return data

    if llm_client is None:
        return data

    # --- LLM prompt ---
    prompt = f"""
You are a data extraction assistant. 
From the following RFP text, extract these fields and return ONLY a valid JSON object:
- due_date (string, keep exactly as written)
- due_time (string or null)
- pre_bid (string or null)
- contact_email (string or null)
- submission_method (string or null)

Text:
\"\"\"{text[:5000]}\"\"\"
"""

    try:
        # Detect Ollama vs OpenAI
        if hasattr(llm_client, "chat") and not hasattr(llm_client, "chat_completions"):
            # --- Ollama client ---
            content = llm_client.chat(
                [
                    {"role": "system", "content": "Extract fields from an RFP and return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            # Parse JSON safely
            try:
                llm_data = json.loads(content)
            except Exception:
                # Try to find JSON inside text
                match = re.search(r"\{.*\}", content, re.DOTALL)
                llm_data = json.loads(match.group(0)) if match else {}
        else:
            # --- OpenAI client ---
            resp = llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            llm_data = json.loads(resp.choices[0].message.content)

        # Merge AI + regex results (regex wins if conflict)
        merged = {**llm_data, **data}
        return merged

    except Exception as e:
        print(f"[AI extract_fields] LLM parse error: {e}")
        return data
