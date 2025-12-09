from typing import Any, Dict, List


def run_basic_checks(answer: str, question: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight compliance checks: length and required flag coverage.
    """
    issues: List[Dict[str, str]] = []
    wc = len((answer or "").split())
    max_words = question.get("max_words") or 0

    if max_words and wc > max_words:
        issues.append({"type": "length", "detail": f"Answer exceeds max_words ({wc} > {max_words})"})
    if question.get("required") and wc < 20:
        issues.append({"type": "completeness", "detail": "Answer may be too short for a required question"})

    # Simple score: start at 0.9 and subtract per issue
    score = 0.9 - 0.15 * len(issues)
    score = max(0.1, min(score, 1.0))
    return {"score": round(score, 2), "issues": issues}
