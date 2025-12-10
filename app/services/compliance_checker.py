from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ComplianceResult:
    checks: List[Check] = field(default_factory=list)
    score: float = 0.0


class ComplianceChecker:
    """
    Multi-dimensional compliance checks for generated answers.
    The requirements dict may include:
      - word_limit (int)
      - page_limit (int)
      - must_include (list[str])
      - prohibited (list[str])
      - company_name (str)
      - rfp_number (str)
      - sub_questions (list[str])
    """

    WORDS_PER_PAGE_ESTIMATE = 500  # rough heuristic for page limits

    def check_all(self, response: str, requirements: Dict[str, Any]) -> ComplianceResult:
        checks: List[Check] = []
        checks.append(self._check_word_limit(response, requirements.get("word_limit")))
        checks.append(self._check_page_limit(response, requirements.get("page_limit")))
        checks.append(self._check_required_elements(response, requirements.get("must_include") or []))
        checks.append(self._check_prohibited_terms(response, requirements.get("prohibited") or []))
        checks.append(self._check_uses_company_name(response, requirements.get("company_name")))
        checks.append(self._check_references_rfp_number(response, requirements.get("rfp_number")))
        checks.append(self._check_answers_all_parts(response, requirements.get("sub_questions") or []))
        score = self._calculate_score(checks)
        return ComplianceResult(checks=checks, score=score)

    def _check_word_limit(self, response: str, limit: Any) -> Check:
        try:
            limit_val = int(limit) if limit is not None else None
        except Exception:
            limit_val = None
        wc = len((response or "").split())
        if limit_val:
            passed = wc <= limit_val
            detail = f"{wc} words / limit {limit_val}"
        else:
            passed = True
            detail = f"{wc} words"
        return Check(name="word_limit", passed=passed, detail=detail)

    def _check_page_limit(self, response: str, limit: Any) -> Check:
        try:
            limit_val = int(limit) if limit is not None else None
        except Exception:
            limit_val = None
        if not limit_val:
            return Check(name="page_limit", passed=True, detail="No page limit provided")
        est_pages = len((response or "").split()) / float(self.WORDS_PER_PAGE_ESTIMATE)
        passed = est_pages <= limit_val
        detail = f"~{est_pages:.2f} pages / limit {limit_val}"
        return Check(name="page_limit", passed=passed, detail=detail)

    def _check_required_elements(self, response: str, elements: List[str]) -> Check:
        missing: List[str] = []
        resp_lower = (response or "").lower()
        for element in elements:
            if element and element.lower() not in resp_lower:
                missing.append(element)
        if missing:
            return Check(
                name="required_elements",
                passed=False,
                detail=f"Missing: {', '.join(missing)}",
            )
        return Check(name="required_elements", passed=True, detail="All required elements present")

    def _check_prohibited_terms(self, response: str, terms: List[str]) -> Check:
        resp_lower = (response or "").lower()
        hits = [t for t in terms if t and t.lower() in resp_lower]
        if hits:
            return Check(name="prohibited_terms", passed=False, detail=f"Contains: {', '.join(hits)}")
        return Check(name="prohibited_terms", passed=True, detail="No prohibited terms detected")

    def _check_uses_company_name(self, response: str, company_name: str | None) -> Check:
        if not company_name:
            return Check(name="company_name", passed=True, detail="No company name provided")
        resp_lower = (response or "").lower()
        if company_name.lower() in resp_lower:
            return Check(name="company_name", passed=True, detail="Company name present")
        return Check(name="company_name", passed=False, detail="Company name missing")

    def _check_references_rfp_number(self, response: str, rfp_number: str | None) -> Check:
        if not rfp_number:
            return Check(name="rfp_number", passed=True, detail="No RFP number provided")
        present = rfp_number.lower() in (response or "").lower()
        return Check(
          name="rfp_number",
          passed=present,
          detail="RFP number referenced" if present else "RFP number missing",
        )

    def _check_answers_all_parts(self, response: str, sub_questions: List[str]) -> Check:
        if not sub_questions:
            return Check(name="completeness", passed=True, detail="No sub-questions provided")
        resp_lower = (response or "").lower()
        missing = [sq for sq in sub_questions if sq and sq.lower() not in resp_lower]
        if missing:
            return Check(name="completeness", passed=False, detail=f"Incomplete: {', '.join(missing)}")
        return Check(name="completeness", passed=True, detail="All parts addressed")

    def _calculate_score(self, checks: List[Check]) -> float:
        if not checks:
            return 1.0
        passed = sum(1 for c in checks if c.passed)
        return round(passed / len(checks), 2)
