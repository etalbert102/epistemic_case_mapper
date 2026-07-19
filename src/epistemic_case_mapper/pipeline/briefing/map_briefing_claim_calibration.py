from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    string_list as _string_list,
)


def calibrate_claim_for_writer(claim: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Return a writer-facing claim surface aligned with source-use limits."""

    original = str(claim or "").strip()
    if not original:
        return {"claim": "", "calibration_notes": [], "not_allowed_terms": []}
    context = _calibration_context(evidence)
    calibrated = original
    notes: list[str] = []
    for pattern, replacement, reason in _RULES:
        next_claim = re.sub(pattern, replacement, calibrated, flags=re.IGNORECASE)
        if next_claim != calibrated:
            calibrated = next_claim
            notes.append(reason)
    if context["must_qualify"] and calibrated != original:
        notes.append("source_appraisal_requires_qualified_wording")
    return {
        "claim": _clean_spacing(calibrated),
        "original_claim": original if _clean_spacing(calibrated) != original else "",
        "calibration_notes": _dedupe(notes),
        "not_allowed_terms": context["avoid_terms"] if notes else [],
    }


def calibrate_text_for_writer(text: str, evidence: dict[str, Any] | None = None) -> str:
    return str(calibrate_claim_for_writer(text, evidence or {}).get("claim") or "")


def _calibration_context(evidence: dict[str, Any]) -> dict[str, Any]:
    appraisal = _dict(evidence.get("source_appraisal"))
    allowed = _dict(evidence.get("allowed_wording") or appraisal.get("allowed_wording"))
    warnings = _string_list(evidence.get("source_use_warnings") or appraisal.get("source_use_warnings"))
    avoid_terms = _string_list(allowed.get("avoid_terms"))
    must_qualify = (
        allowed.get("causal_language_allowed") is False
        or "association_not_causation" in warnings
        or bool(_string_list(allowed.get("must_qualify_with")))
    )
    return {
        "must_qualify": must_qualify,
        "avoid_terms": _dedupe([*avoid_terms, *_DEFAULT_NOT_ALLOWED]) if must_qualify else avoid_terms,
    }


def _clean_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


_DEFAULT_NOT_ALLOWED = [
    "proves",
    "causes",
    "safe",
    "safety",
    "independent",
    "fully accounted for",
]

_RULES: tuple[tuple[str, str, str], ...] = (
    (
        r"\bestablish(?:es|ing)?\s+a\s+baseline\s+of\s+safety\b",
        "supports a bounded neutral risk read",
        "softened_safety_claim",
    ),
    (
        r"\bsafe\s+for\s+heart\s+health\b",
        "not clearly associated with higher cardiovascular risk in the stated scope",
        "softened_safety_claim",
    ),
    (
        r"\bsafe\s+profile\b",
        "bounded neutral risk profile",
        "softened_safety_claim",
    ),
    (
        r"\bsafety\s+profile\b",
        "risk profile",
        "softened_safety_claim",
    ),
    (
        r"\bcan\s+be\s+consumed\s+safely\b",
        "can be consumed without a clear adverse signal in the stated scope",
        "softened_safety_claim",
    ),
    (
        r"\bcan\s+safely\s+([a-z]+)\b",
        r"can \1 within the stated scope",
        "softened_safety_claim",
    ),
    (
        r"\bsafety\b",
        "risk",
        "softened_safety_claim",
    ),
    (
        r"\bsafe\b",
        "not clearly harmful in the stated scope",
        "softened_safety_claim",
    ),
    (
        r"\bsafely\b",
        "with stated-scope qualification",
        "softened_safety_claim",
    ),
    (
        r"\bdoes\s+not\s+generally\s+support\s+an\s+association\b",
        "does not clearly show a consistent association",
        "softened_no_association_claim",
    ),
    (
        r"\bhave\s+not\s+generally\s+supported\s+an\s+association\b",
        "have not clearly shown a consistent association",
        "softened_no_association_claim",
    ),
    (
        r"\bis\s+specifically\s+tied\s+to\b",
        "appears related to",
        "softened_mechanistic_claim",
    ),
    (
        r"\bis\s+independent\s+of\b",
        "is not fully explained by",
        "softened_independence_claim",
    ),
    (
        r"\bindependent\s+of\b",
        "not fully explained by",
        "softened_independence_claim",
    ),
    (
        r"\bis\s+fully\s+accounted\s+for\s+by\b",
        "may be partly accounted for by",
        "softened_accounting_claim",
    ),
    (
        r"\bfully\s+accounted\s+for\s+by\b",
        "partly accounted for by",
        "softened_accounting_claim",
    ),
)
