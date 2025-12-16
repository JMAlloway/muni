import json
import re
import textwrap
import logging
from typing import Any, Dict, List, Tuple

from app.ai.client import get_llm_client
from app.services.extraction_cache import ExtractionCache

logger = logging.getLogger("rfp_extractor")

# Tunable constants
MAX_WORDS_PER_CHUNK = 3500  # heuristic for token limits
MAX_PROMPT_CHARS = 12000
MAX_CHUNKS = 12  # limit LLM calls on very large docs
MAX_TOTAL_CHARS = 400000  # early truncation guard (~60-70k words)

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


def _chunk_text(txt: str, max_words: int = MAX_WORDS_PER_CHUNK, max_chunks: int = MAX_CHUNKS) -> Tuple[List[str], bool]:
    """
    Split text into word-limited chunks without loading all words into memory at once.
    Returns (chunks, truncated_flag) where truncated_flag is True if max_chunks cap was hit.
    """
    if not txt:
        return [], False

    chunks: List[str] = []
    current: List[str] = []
    truncated = False
    count = 0

    for match in re.finditer(r"\S+", txt):
        current.append(match.group(0))
        count += 1
        if count >= max_words:
            chunks.append(" ".join(current))
            current = []
            count = 0
            if max_chunks and len(chunks) >= max_chunks:
                truncated = True
                break

    if current and (not max_chunks or len(chunks) < max_chunks):
        chunks.append(" ".join(current))

    return chunks, truncated


def _trim_text(raw: str) -> Tuple[str, bool]:
    """
    Apply a hard character cap before heavy processing to avoid memory blowups.
    Returns (trimmed_text, was_truncated).
    """
    if not raw:
        return "", False
    if len(raw) <= MAX_TOTAL_CHARS:
        return raw, False
    return raw[:MAX_TOTAL_CHARS], True


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


def _normalize_string(s: str) -> str:
    """Normalize a string for deduplication comparison."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _is_duplicate_item(new_item: Any, existing_items: List[Any]) -> bool:
    """Check if an item already exists in the list (handles both strings and dicts)."""
    if isinstance(new_item, str):
        normalized_new = _normalize_string(new_item)
        for existing in existing_items:
            if isinstance(existing, str) and _normalize_string(existing) == normalized_new:
                return True
        return False
    elif isinstance(new_item, dict):
        new_name = new_item.get("name") or new_item.get("title") or new_item.get("event") or ""
        if new_name:
            normalized_new = _normalize_string(str(new_name))
            for existing in existing_items:
                if isinstance(existing, dict):
                    existing_name = existing.get("name") or existing.get("title") or existing.get("event") or ""
                    if existing_name and _normalize_string(str(existing_name)) == normalized_new:
                        return True
        return False
    return new_item in existing_items


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
                    for v in val:
                        if v and not _is_duplicate_item(v, out[key]):
                            out[key].append(v)
            else:
                if val and isinstance(val, str) and len(val) > len(out[key]):
                    out[key] = val
    return out


def _merge_discovery(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge discovery results across chunks.
    """
    base: Dict[str, Any] = {
        "document_type": "",
        "sections": [],
        "response_items": [],
        "deadlines": [],
        "submission": {},
        "evaluation_weights": [],
        "required_response_sections": [],
    }
    if not results:
        return base
    for res in results:
        if not isinstance(res, dict):
            continue
        base["document_type"] = base["document_type"] or res.get("document_type", "")
        for key in ("sections", "response_items", "deadlines", "evaluation_weights", "required_response_sections"):
            val = res.get(key) or []
            if isinstance(val, list):
                base[key].extend(val)
        submission = res.get("submission")
        if isinstance(submission, dict) and submission and not base["submission"]:
            base["submission"] = submission
    return base


class RfpExtractor:
    """LLM-backed extractor for RFP documents into EasyRFP JSON schema."""

    def __init__(self):
        self.llm = get_llm_client()
        self.cache = ExtractionCache()

    def discover(self, text: str) -> Dict[str, Any]:
        trimmed, _ = _trim_text(text)
        cleaned = _clean_text(trimmed)
        if not cleaned or not self.llm:
            return {}
        chunks, _ = _chunk_text(cleaned, max_words=MAX_WORDS_PER_CHUNK, max_chunks=1)
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
        trimmed, _ = _trim_text(text)
        cleaned = _clean_text(trimmed)
        if not cleaned:
            return _merge_json([])

        chunks, chunk_limited = _chunk_text(cleaned, max_words=MAX_WORDS_PER_CHUNK)
        if not chunks:
            chunks = [cleaned]

        results: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            if not self.llm:
                break
            if MAX_CHUNKS and idx >= MAX_CHUNKS:
                break
            try:
                msgs = _build_extraction_prompt(chunk)
                logger.debug("rfp_extractor.extract_json chunk=%s words=%s", idx + 1, len(chunk.split()))
                resp = self.llm.chat(msgs, temperature=0)
                parsed = _safe_load_json(resp)
                if isinstance(parsed, dict):
                    results.append(parsed)
            except Exception as exc:
                logger.warning("rfp_extractor.extract_json parse failed: %s", exc)
                continue

        merged = _merge_json(results)
        if chunk_limited or (MAX_CHUNKS and len(chunks) >= MAX_CHUNKS):
            merged.setdefault("warning", "Extraction capped to first chunks; content may be partial.")
        return merged

    def _extract_combined(self, text: str, truncated_input: bool = False) -> Dict[str, Any]:
        """
        Single LLM call returning both discovery + extracted blocks.
        """
        cleaned = _clean_text(text)
        if not cleaned or not self.llm:
            return {"discovery": {}, "extracted": _merge_json([])}

        chunks, chunk_limited = _chunk_text(cleaned, max_words=MAX_WORDS_PER_CHUNK, max_chunks=MAX_CHUNKS)
        if not chunks:
            chunks = [cleaned]

        discoveries: List[Dict[str, Any]] = []
        extracted_chunks: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for idx, chunk in enumerate(chunks):
            if MAX_CHUNKS and idx >= MAX_CHUNKS:
                chunk_limited = True
                break
            try:
                logger.debug("rfp_extractor.extract_combined chunk=%s words=%s", idx + 1, len(chunk.split()))
                resp = self.llm.chat(_build_combined_prompt(chunk), temperature=0)
                parsed = _safe_load_json(resp)
                if isinstance(parsed, dict):
                    disc = parsed.get("discovery") or {}
                    ext = parsed.get("extracted") or {}
                    discoveries.append(disc if isinstance(disc, dict) else {})
                    if isinstance(ext, dict):
                        extracted_chunks.append(ext)
            except Exception as exc:
                logger.warning("rfp_extractor.extract_combined failed chunk=%s: %s", idx + 1, exc)
                continue

        if truncated_input:
            warnings.append(f"Input truncated to first {MAX_TOTAL_CHARS} characters for processing.")
        if chunk_limited:
            warnings.append(f"Only the first {MAX_CHUNKS} chunks were processed; remaining text was skipped.")

        merged_extracted = _merge_json(extracted_chunks)
        merged_discovery = _merge_discovery(discoveries)
        result = {"discovery": merged_discovery, "extracted": merged_extracted}
        if warnings:
            result["warning"] = " ".join(warnings)
        return result

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
        trimmed, truncated = _trim_text(text)
        cleaned = _clean_text(trimmed)
        # Pass 1: main combined extraction
        combined = self._extract_combined(cleaned, truncated_input=truncated)
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
        trimmed, truncated = _trim_text(text)
        cached = await self.cache.get(trimmed)
        if cached:
            return cached
        result = self.extract_json(trimmed)
        if truncated:
            result.setdefault("warning", "Input truncated before caching; content may be partial.")
        await self.cache.set(trimmed, result)
        return result

    async def extract_all_cached(self, text: str) -> Dict[str, Any]:
        """
        Async helper wrapping extract_all with caching on extracted payload.
        """
        trimmed, truncated = _trim_text(text)
        cached = await self.cache.get(trimmed)
        if cached and isinstance(cached, dict) and cached.get("extracted"):
            # cache may store just extracted; normalize shape
            return {"discovery": cached.get("discovery") or {}, "extracted": cached.get("extracted") or cached}
        result = self.extract_all(trimmed)
        if truncated:
            result.setdefault("warning", "Input truncated before caching; content may be partial.")
        await self.cache.set(trimmed, result)
        return result
