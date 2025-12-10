import json
import re
import textwrap
from typing import Any, Dict, List

from app.ai.client import get_llm_client

# Tunable constants
MAX_WORDS_PER_CHUNK = 3500  # heuristic for token limits
MAX_PROMPT_CHARS = 12000


def _clean_text(raw: str) -> str:
    txt = raw or ""
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
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


def _chunk_text(txt: str, max_words: int = MAX_WORDS_PER_CHUNK) -> List[str]:
    words = txt.split()
    if not words:
        return []
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


DISCOVERY_PROMPT = """
Analyze this RFP document and identify:
1. All section headings and their hierarchy
2. Questions that require responses (numbered items, fill-in blanks, tables)
3. Submission requirements (deadlines, formats, page limits)
4. Evaluation criteria with weights if provided
5. Required forms/attachments mentioned

Return JSON:
{
  "document_type": "RFQ|RFP|IFB|SOW|other",
  "sections": [{"title": "", "page": null, "has_questions": false}],
  "response_items": [{"id": "", "text": "", "type": "narrative|table|form|attachment", "word_limit": null, "page_limit": null, "points": null}],
  "deadlines": [{"event": "", "date": "", "time": "", "timezone": ""}],
  "submission": {"method": "email|portal|mail", "copies": null, "format": "", "address": ""},
  "evaluation_weights": [{"criterion": "", "weight": null}]
}
""".strip()


EXTRACTION_SCHEMA_PROMPT = """
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
""".strip()


def _build_discovery_prompt(text: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": "You are an expert RFP analyst. Discover structure of the document."},
        {
            "role": "user",
            "content": f"{DISCOVERY_PROMPT}\n\nSource text:\n\"\"\"\n{text[:MAX_PROMPT_CHARS]}\n\"\"\"\n",
        },
    ]


def _build_extraction_prompt(text: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": "You are an expert RFP analyst. Extract key fields as structured JSON."},
        {
            "role": "user",
            "content": f"{EXTRACTION_SCHEMA_PROMPT}\n\nSource text:\n\"\"\"\n{text[:MAX_PROMPT_CHARS]}\n\"\"\"\n",
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

    def discover(self, text: str) -> Dict[str, Any]:
        cleaned = _clean_text(text)
        if not cleaned or not self.llm:
            return {}
        chunks = _chunk_text(cleaned, max_words=MAX_WORDS_PER_CHUNK)
        first_chunk = chunks[0] if chunks else cleaned
        try:
            resp = self.llm.chat(_build_discovery_prompt(first_chunk), temperature=0)
            parsed = json.loads(resp)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def extract_json(self, text: str) -> Dict[str, Any]:
        cleaned = _clean_text(text)
        if not cleaned:
            return _merge_json([])

        chunks = _chunk_text(cleaned, max_words=MAX_WORDS_PER_CHUNK)
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

    def extract_all(self, text: str) -> Dict[str, Any]:
        discovery = self.discover(text)
        extracted = self.extract_json(text)
        return {
            "discovery": discovery,
            "extracted": extracted,
        }
