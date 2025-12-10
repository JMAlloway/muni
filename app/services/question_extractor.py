import re
from typing import Any, Dict, List


def extract_response_items(text: str) -> List[Dict[str, Any]]:
    """
    Heuristic extraction of response items/questions from RFP text.
    Flags numbered/lettered items, question marks, action verbs, and placeholders.
    """
    if not text:
        return []

    lines = text.splitlines()
    questions: List[Dict[str, Any]] = []
    idx = 1

    numbered = re.compile(r"^\s*(\d+)[\.\)]\s+(.+)")
    lettered = re.compile(r"^\s*([a-zA-Z])[\.\)]\s+(.+)")
    action = re.compile(r"(describe|explain|provide|list|detail|outline|demonstrate)\s+(.+)", re.IGNORECASE)
    placeholder = re.compile(r"\[.+?\]")

    for ln in lines:
        line = ln.strip()
        if not line:
            continue

        matched_text = None
        if numbered.match(line):
            matched_text = numbered.match(line).group(2)
        elif lettered.match(line):
            matched_text = lettered.match(line).group(2)
        elif "?" in line:
            matched_text = line
        else:
            act = action.search(line)
            if act:
                matched_text = line
            elif placeholder.search(line):
                matched_text = line

        if matched_text:
            qid = f"Q{idx}"
            idx += 1
            questions.append(
                {
                    "id": qid,
                    "text": matched_text.strip(),
                    "type": "narrative",
                    "word_limit": None,
                    "section": None,
                    "points": None,
                    "auto_detected": True,
                    "confidence": 0.75,
                }
            )

    return questions
