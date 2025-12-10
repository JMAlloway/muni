from typing import Any, Dict, List

from app.services.compliance_checker import ComplianceChecker


def run_basic_checks(answer: str, question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Multi-dimensional compliance checks: length, required elements, prohibited terms, references, and completeness.
    Returns score plus failing issues for quick surfacing in the UI.
    """
    checker = ComplianceChecker()
    requirements: Dict[str, Any] = {
        "word_limit": question.get("max_words") or question.get("word_limit"),
        "page_limit": question.get("page_limit"),
        "must_include": question.get("must_include") or question.get("required_elements") or [],
        "prohibited": question.get("prohibited") or [],
        "company_name": question.get("company_name"),
        "rfp_number": question.get("rfp_number") or question.get("opportunity_id"),
        "sub_questions": question.get("sub_questions") or [],
    }
    result = checker.check_all(answer or "", requirements)
    failing = [
        {"type": c.name, "detail": c.detail}
        for c in result.checks
        if not c.passed
    ]
    return {"score": result.score, "issues": failing, "checks": [c.__dict__ for c in result.checks]}
