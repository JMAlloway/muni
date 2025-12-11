import json
import re
import textwrap
import logging
from typing import Any, Dict, List

from app.ai.client import get_llm_client
from app.services.extraction_cache import ExtractionCache

logger = logging.getLogger("rfp_extractor")

# Tunable constants
MAX_WORDS_PER_CHUNK = 3500  # heuristic for token limits
MAX_PROMPT_CHARS = 12000

def _has_useful_content(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    extracted = payload.get("extracted") or payload
    if not isinstance(extracted, dict):
        return False
    fields = [
        extracted.get("summary"),
        extracted.get("scope_of_work"),
        extracted.get("submission_instructions"),
    ]
    lists = [
        extracted.get("required_documents") or [],
        extracted.get("required_forms") or [],
        extracted.get("compliance_terms") or [],
        extracted.get("deadlines") or [],
        extracted.get("contacts") or [],
    ]
    if any(f and str(f).strip() for f in fields):
        return True
    if any(isinstance(lst, list) and len(lst) for lst in lists):
        return True
    return False


def _safe_load_json(resp: str) -> Dict[str, Any]:
    """
    Attempt to parse JSON from an LLM response, handling blank strings and fenced blocks.
    """
    if not resp:
        raise ValueError("Empty response")
    txt = resp.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if "\n" in txt:
            parts = txt.split("\n", 1)
            if parts and parts[0].lower().startswith("json"):
                txt = parts[1]
            else:
                txt = "\n".join(parts[1:]) if len(parts) > 1 else parts[0]
    if not txt.startswith("{") and not txt.startswith("["):
        brace_start = txt.find("{")
        if brace_start != -1:
            txt = txt[brace_start:]
    return json.loads(txt)


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

COMBINED_PROMPT = """
You are an expert RFP analyst. Analyze this solicitation document and extract structured information.

CRITICAL: Separate what the proposer must WRITE vs what they must ATTACH.

Return JSON with this structure:
{
  "extracted": {
    "title": "RFP title",
    "agency": "Issuing agency name",
    "summary": "2-3 sentence summary of what is being solicited",
    "scope_of_work": "Brief description of the work/services required",
    
    "narrative_sections": [
      {
        "name": "Exact section name from RFP",
        "requirements": "What must be included in this section",
        "page_limit": null,
        "word_limit": null,
        "points": null
      }
    ],
    
    "attachments_forms": [
      "W-9 Form",
      "Insurance Certificate",
      "Non-Collusion Affidavit"
    ],
    
    "deadlines": [
      {"event": "Proposal Due", "date": "2024-03-15", "time": "2:00 PM", "timezone": "EST"}
    ],
    
    "submission_instructions": "How and where to submit",
    "evaluation_criteria": ["Criteria 1 - 30%", "Criteria 2 - 25%"],
    "contacts": [{"name": "", "email": "", "phone": ""}]
  }
}

INSTRUCTIONS FOR narrative_sections:
- These are sections the proposer must WRITE (AI will generate content for these)
- Look for: "provide a narrative", "describe your approach", "explain your qualifications", 
  "include a description of", "submit a statement of", "technical approach", "management plan",
  "personnel qualifications", "past performance", "project understanding"
- Extract the EXACT requirements stated for each section
- Include any page/word limits mentioned

INSTRUCTIONS FOR attachments_forms:
- These are pre-made documents to ATTACH (user already has these, AI does NOT generate)
- Look for: "attach completed form", "include certificate", "submit signed affidavit",
  "W-9", "insurance certificate", "bond", "license", "registration"
- Just list the form/document names

Be thorough - RFPs often bury requirements throughout the document.
""".strip()

NARRATIVE_EXTRACTION_PROMPT = """
Analyze this RFP and identify ALL sections where the proposer must write narrative content.

For each narrative section found, extract:
1. Section name (exactly as written in the RFP)
2. What the section must address/include
3. Page or word limits (if specified)
4. Evaluation points/weight (if specified)
5. Any specific formatting requirements

Common narrative sections include:
- Executive Summary / Cover Letter
- Company Background / Qualifications
- Technical Approach / Methodology  
- Project Understanding / Scope
- Personnel / Key Staff / Team
- Past Performance / Experience / References
- Management Plan / Schedule
- Cost Narrative (not the pricing, but explanation)

Return JSON array:
[
  {
    "name": "Brief Narrative",
    "requirements": "Describe proposer background, relevant experience, and approach to the project. Must address understanding of scope.",
    "page_limit": 3,
    "word_limit": null,
    "points": 25,
    "formatting": "12pt font, 1 inch margins"
  }
]

Extract EVERY narrative section mentioned, even if requirements are vague.
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


def _build_combined_prompt(text: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": "You are an expert RFP analyst. Return discovery + extracted JSON in one response."},
        {
            "role": "user",
            "content": f"{COMBINED_PROMPT}\n\nSource text:\n\"\"\"\n{text[:MAX_PROMPT_CHARS]}\n\"\"\"\n",
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
        "narrative_sections": [],
        "attachments_forms": [],
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
        self.cache = ExtractionCache()

    def discover(self, text: str) -> Dict[str, Any]:
        cleaned = _clean_text(text)
        if not cleaned or not self.llm:
            return {}
        chunks = _chunk_text(cleaned, max_words=MAX_WORDS_PER_CHUNK)
        first_chunk = chunks[0] if chunks else cleaned
        try:
            logger.debug("rfp_extractor.discover start words=%s", len(first_chunk.split()))
            resp = self.llm.chat(_build_discovery_prompt(first_chunk), temperature=0)
            parsed = _safe_load_json(resp)
            logger.debug("rfp_extractor.discover ok keys=%s", list(parsed.keys()) if isinstance(parsed, dict) else [])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            logger.exception("rfp_extractor.discover failed")
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
                logger.debug("rfp_extractor.extract_json chunk words=%s", len(chunk.split()))
                resp = self.llm.chat(msgs, temperature=0)
                parsed = _safe_load_json(resp)
                if isinstance(parsed, dict):
                    results.append(parsed)
            except Exception as exc:
                logger.warning("rfp_extractor.extract_json parse failed: %s", exc)
                continue

        return _merge_json(results)

    def _extract_combined(self, text: str) -> Dict[str, Any]:
        """
        Single LLM call returning both discovery + extracted blocks.
        """
        cleaned = _clean_text(text)
        if not cleaned or not self.llm:
            return {"discovery": {}, "extracted": _merge_json([])}
        try:
            logger.debug("rfp_extractor.extract_combined start")
            resp = self.llm.chat(_build_combined_prompt(cleaned), temperature=0)
            parsed = _safe_load_json(resp)
            if isinstance(parsed, dict):
                return {
                    "discovery": parsed.get("discovery") or {},
                    "extracted": parsed.get("extracted") or _merge_json([]),
                }
        except Exception as exc:
            logger.warning("rfp_extractor.extract_combined failed: %s", exc)
        # Fallback to empty discovery + merged extraction to avoid crash
        return {"discovery": {}, "extracted": _merge_json([])}

    def _extract_narratives(self, text: str) -> List[Dict[str, Any]]:
        """
        Focused extraction of narrative sections when the main extraction misses them.
        """
        cleaned = _clean_text(text)
        if not cleaned or not self.llm:
            return []
        try:
            resp = self.llm.chat(
                [
                    {"role": "system", "content": "You are an expert RFP analyst."},
                    {"role": "user", "content": f"{NARRATIVE_EXTRACTION_PROMPT}\n\nSource text:\n\"\"\"\n{cleaned[:MAX_PROMPT_CHARS]}\n\"\"\"\n"},
                ],
                temperature=0,
            )
            parsed = _safe_load_json(resp)
            if isinstance(parsed, list):
                return parsed
        except Exception as exc:
            logger.warning("rfp_extractor._extract_narratives failed: %s", exc)
        return []

    def extract_all(self, text: str) -> Dict[str, Any]:
        cleaned = _clean_text(text)
        # Pass 1: main combined extraction
        combined = self._extract_combined(cleaned)
        extracted = combined.get("extracted") or {}

        # Pass 2: if narratives missing, run focused extraction
        if not extracted.get("narrative_sections"):
            narratives = self._extract_narratives(cleaned)
            if narratives:
                extracted["narrative_sections"] = narratives
                combined["extracted"] = extracted

        return combined

    async def extract_json_cached(self, text: str) -> Dict[str, Any]:
        """
        Async helper that checks cache before running extract_json.
        """
        cached = await self.cache.get(text)
        if cached:
            return cached
        result = self.extract_json(text)
        await self.cache.set(text, result)
        return result

    async def extract_all_cached(self, text: str) -> Dict[str, Any]:
        """
        Async helper wrapping extract_all with caching on extracted payload.
        """
        cached = await self.cache.get(text)
        if cached and isinstance(cached, dict) and cached.get("extracted"):
            # cache may store just extracted; normalize shape
            return {"discovery": cached.get("discovery") or {}, "extracted": cached.get("extracted") or cached}
        result = self.extract_all(text)
        await self.cache.set(text, result)
        return result
