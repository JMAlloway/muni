# app/ai/extract_fields.py
import re
import json
from typing import Dict, Any

DATE_PAT = re.compile(
    r"(?:due|closing|proposal(?:s)? due|bids? due)\s*[:\-]?\s*"
    r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

TIME_PAT = re.compile(
    r"(\d{1,2}:\d{2}\s*(?:a\.m\.|p\.m\.|am|pm)?)",
    re.IGNORECASE,
)


def _regex_extract(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not text:
        return data

    m_date = DATE_PAT.search(text)
    if m_date:
        data["due_date_text"] = m_date.group(1).strip()

    m_time = TIME_PAT.search(text)
    if m_time:
        data["due_time_text"] = m_time.group(1).strip()

    return data


def extract_key_fields(text: str, llm_client=None) -> Dict[str, Any]:
    text = text or ""
    data = _regex_extract(text)

    if not llm_client:
        return data

    try:
        prompt = (
            "Extract structured info from the following municipal RFP/RFQ text. "
            "Return JSON with keys: title, due_date, due_time, location, contact, email. "
            "If not present, use null.\n\n"
            f"{text[:3500]}"
        )

        if hasattr(llm_client, "chat") and callable(getattr(llm_client, "chat")) and not hasattr(llm_client, "chat_completions"):
            raw = llm_client.chat(
                [
                    {"role": "system", "content": "You extract fields and return JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                format="json",  # newer Ollama may ignore this; that's ok
            )
            try:
                llm_data = json.loads(raw)
            except Exception:
                # older /api/generate will give plain text -> ignore
                llm_data = {}
        else:
            resp = llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            llm_data = json.loads(resp.choices[0].message.content)

        merged = {**llm_data, **data}
        return merged
    except Exception as e:
        print(f"[AI extract_fields] LLM parse error: {e}")
        return data
