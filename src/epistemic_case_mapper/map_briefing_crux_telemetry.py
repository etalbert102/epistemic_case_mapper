from __future__ import annotations

import re
from typing import Any


GENERIC_CRUX_PHRASES = (
    "decision-changing condition",
    "impact of specific health concerns",
    "causal attribution of observed effects",
    "specific concern",
    "condition changes",
    "new evidence showed",
)


def build_crux_quality_telemetry(
    *,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    briefing_text: str,
) -> dict[str, Any]:
    cruxes = _crux_rows(scaffold)
    claim_text = " ".join(_claim_texts(prioritized_map) or _claim_texts(candidate_map))
    relation_crux_count = sum(1 for relation in _relations(prioritized_map) if str(relation.get("relation_type")) == "crux_for")
    rows = [_score_crux(row, claim_text, briefing_text) for row in cruxes]
    concrete_count = sum(1 for row in rows if row["concrete"])
    decision_changing_count = sum(1 for row in rows if row["decision_changing"])
    anchored_count = sum(1 for row in rows if row["anchored_to_map"])
    generic_count = sum(1 for row in rows if row["generic"])
    count = len(rows)
    score = 100
    if count == 0:
        score = 30 if relation_crux_count else 20
    else:
        score -= max(0, 2 - concrete_count) * 18
        score -= max(0, 2 - decision_changing_count) * 16
        score -= max(0, 1 - anchored_count) * 14
        score -= generic_count * 12
    if relation_crux_count and count == 0:
        score -= 20
    status = "strong" if score >= 85 else "usable_with_review" if score >= 65 else "needs_crux_work"
    return {
        "schema_id": "crux_quality_telemetry_v1",
        "status": status,
        "score": max(0, min(100, score)),
        "crux_count": count,
        "relation_crux_count": relation_crux_count,
        "concrete_crux_count": concrete_count,
        "decision_changing_crux_count": decision_changing_count,
        "anchored_crux_count": anchored_count,
        "generic_crux_count": generic_count,
        "crux_rows": rows,
        "recommended_intervention": _recommended_intervention(status, generic_count, anchored_count, decision_changing_count),
    }


def _crux_rows(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    rows = [row for row in synthesis.get("cruxes", []) if isinstance(row, dict)]
    if rows:
        return rows
    contract = scaffold.get("crux_contract", {}) if isinstance(scaffold.get("crux_contract"), dict) else {}
    return [row for row in contract.get("cruxes", []) if isinstance(row, dict)]


def _score_crux(row: dict[str, Any], claim_text: str, briefing_text: str) -> dict[str, Any]:
    crux = str(row.get("crux") or row.get("candidate_crux") or "").strip()
    current = str(row.get("current_read", "")).strip()
    would_change = str(row.get("would_change_if", "")).strip()
    why = str(row.get("why_it_matters", "")).strip()
    combined = " ".join((crux, current, would_change, why))
    terms = _content_terms(combined)
    concrete = len(_content_terms(crux)) >= 3 and not _generic_crux(crux)
    decision_changing = _decision_changing(combined)
    anchored = _term_overlap(terms, _content_terms(claim_text)) >= 2 or _term_overlap(_content_terms(crux), _content_terms(briefing_text)) >= 2
    return {
        "crux": crux,
        "concrete": concrete,
        "decision_changing": decision_changing,
        "anchored_to_map": anchored,
        "generic": _generic_crux(combined),
        "content_term_count": len(set(terms)),
    }


def _generic_crux(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in GENERIC_CRUX_PHRASES):
        return True
    terms = set(_content_terms(text))
    return len(terms) < 3 or terms <= {"evidence", "decision", "condition", "interpretation", "risk"}


def _decision_changing(text: str) -> bool:
    lowered = text.lower()
    markers = ("would change", "change if", "turns on", "depends on", "if evidence", "if new", "would shift", "materially affect")
    return any(marker in lowered for marker in markers)


def _recommended_intervention(status: str, generic_count: int, anchored_count: int, decision_changing_count: int) -> str:
    if status == "strong":
        return "No deterministic crux intervention required."
    if generic_count:
        return "Regenerate cruxes from graph tensions using claim-specific nouns and explicit would-change-if clauses."
    if anchored_count == 0:
        return "Require each crux to cite or overlap a load-bearing claim or relation endpoint."
    if decision_changing_count < 2:
        return "Rewrite cruxes as concrete uncertainties that would change the decision recommendation."
    return "Review crux rows for specificity and map anchoring."


def _claim_texts(candidate_map: dict[str, Any]) -> list[str]:
    return [str(claim.get("claim") or claim.get("text") or "") for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]


def _content_terms(text: str) -> list[str]:
    stop = {
        "the", "and", "that", "with", "from", "this", "these", "those", "were", "was", "are", "for", "into",
        "than", "would", "change", "evidence", "decision", "current", "read", "new", "showed",
    }
    return [term for term in re.findall(r"[a-z0-9]{3,}", text.lower()) if term not in stop]


def _term_overlap(left: list[str], right: list[str]) -> int:
    return len(set(left) & set(right))
