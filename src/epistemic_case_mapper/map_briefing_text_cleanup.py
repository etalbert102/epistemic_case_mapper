from __future__ import annotations

import re


def replace_internal_reader_phrases(text: str) -> str:
    replacements = {
        "mapped support": "available evidence",
        "map-backed read": "evidence-based read",
        "map-backed default": "best-supported default",
        "decision role": "function in the decision",
        "load-bearing map distinction": "important distinction",
        "preserved as a load-bearing map distinction": "important for interpreting the recommendation",
        "not specified": "not established by this packet",
        "full map-backed detail": "full source-grounded detail",
    }
    cleaned = text
    for phrase, replacement in replacements.items():
        cleaned = re.sub(re.escape(phrase), replacement, cleaned, flags=re.IGNORECASE)
    person_group = r"(?:participants|people|adults|children|individuals|patients|respondents|workers)"
    return re.sub(
        rf"\b({person_group}\b[^.\n;:]{{0,140}}?)\s+WHO\s+(were|was|are|is|had|have)\b",
        lambda match: f"{match.group(1)} who {match.group(2)}",
        cleaned,
        flags=re.IGNORECASE,
    )
