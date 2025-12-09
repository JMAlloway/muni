import json
import math
import re
import textwrap
from typing import Any, Dict, List

from app.ai.client import get_llm_client


def _clean_text(raw: str) -> str:
    txt = raw or ""
    # Collapse multiple newlines and spaces
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    # Remove common page headers/footers repeating lines
    lines = txt.splitlines()
    if not lines:
        return ""
    freq: Dict[str, int] = {}
    for ln in lines:
        key = ln.strip()
        if len(key) > 5:
            freq[key] = freq.get(key, 0) + 1
    headers = {k for k, v in freq.items() if v > 3 and len(k) < 120}
    filtered = [ln for ln in lines if ln.strip() not in headers]
    return "\n".join(filtered).strip()


def _chunk_text(txt: str, max_words: int = 3500) -> List[str]:
    words = txt.split()
    chunks = []
    if not words:
        return chunks
    step = max_words
    for i in range(0, len(words), step):
        piece = " ".join(words[i : i + step])
        chunks.append(piece)
    return chunks


def _schema_description() -> str:
    return textwrap.dedent(
        """
        Return strict JSON with these keys:
        {
          "title": "",
          "agency": "",
          "summary": "",
          "scope_of_work": "",
          "contractor_requirements": [],
          "training_requirements": [],
          "insurance_limits": "",
          "required_documents": [],
          "submission_instructions": "",
          "deadlines": [],
          "contacts": [],
          "evaluation_criteria": [],
          "required_forms": [],
          "compliance_terms": [],
          "red_flags": []
        }
        - arrays must be lists of strings (or objects if obvious like contacts with name/email/phone).
        - If unknown, use "" or [].
        """
    ).strip()


def _build_extraction_prompt(text: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": "You are an expert RFP analyst. Extract key fields as structured JSON."},
        {
            "role": "user",
            "content": f"""
{_schema_description()}

Source text:
\"\"\"
{text[:12000]}
\"\"\"
""".strip(),
        },
    ]


def _merge_json(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "title": "",
        "agency": "",
        "summary": "",
        "scope_of_work": "",
        "contractor_requirements": [],
        "training_requirements": [],
        "insurance_limits": "",
        "required_documents": [],
        "submission_instructions": "",
        "deadlines": [],
        "contacts": [],
        "evaluation_criteria": [],
        "required_forms": [],
        "compliance_terms": [],
        "red_flags": [],
    }
    if not results:
        return out
    for res in results:
        if not isinstance(res, dict):
            continue
        for key in out.keys():
            val = res.get(key)
            if isinstance(out[key], list):
                if isinstance(val, list):
                    out[key].extend([v for v in val if v not in out[key]])
            else:
                if val and isinstance(val, str) and len(val) > len(out[key]):
                    out[key] = val
    return out


class RfpExtractor:
    """LLM-backed extractor for RFP documents into EasyRFP JSON schema."""

    def __init__(self):
        self.llm = get_llm_client()

    def extract_json(self, text: str) -> Dict[str, Any]:
        cleaned = _clean_text(text)
        if not cleaned:
            return _merge_json([])

        chunks = _chunk_text(cleaned, max_words=3500)
        if not chunks:
            chunks = [cleaned]

        results: List[Dict[str, Any]] = []
        for chunk in chunks:
            if not self.llm:
                break
            try:
                msgs = _build_extraction_prompt(chunk)
                resp = self.llm.chat(msgs, temperature=0)
                parsed = json.loads(resp)
                if isinstance(parsed, dict):
                    results.append(parsed)
            except Exception:
                continue

        return _merge_json(results)
