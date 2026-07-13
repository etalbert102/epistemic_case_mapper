from __future__ import annotations

import re


def normalize_calibrated_language(text: str) -> str:
    """Soften stock overclaim wording without adding domain-specific facts."""

    normalized = str(text or "")
    for pattern, replacement in _CALIBRATION_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


_CALIBRATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bis considered neutral and safe\b", "is best treated as neutral within the stated scope"),
    (r"\bis treated as neutral and safe\b", "is best treated as neutral within the stated scope"),
    (r"\bSafe for moderate consumption\b", "Neutral for moderate consumption"),
    (r"\bNeutral\s*\(Neutral for moderate consumption\)", "Neutral for moderate consumption"),
    (r"\bhigh-confidence data\b", "large-scale evidence"),
    (r"\bhigh-confidence evidence\b", "strong evidence"),
    (r"\blarge-scale evidence from large-scale\b", "evidence from large-scale"),
    (r"\bbaseline safety\b", "baseline risk read"),
    (r"\bbaseline of safety\b", "baseline interpretation"),
    (r"\bsafe limit\b", "practical reference point"),
    (r"\bsafety profile\b", "risk profile"),
    (r"\bdaily limit\b", "daily reference point"),
    (r"\bis considered safe\b", "is an evidence-bounded reference point"),
    (r"\bproven harmless\b", "not clearly shown to be harmful in the stated scope"),
    (r"\bsafely include\b", "include within the stated scope"),
    (r"\bsafe standard\b", "practical reference point"),
    (r"\bdoes not harm heart health\b", "does not clearly show higher cardiovascular risk in the stated scope"),
    (r"\bis fully accounted for by\b", "may be partly accounted for by"),
    (r"\bfully accounted for by\b", "partly accounted for by"),
    (r"\bindependent of\b", "not fully explained by"),
)
