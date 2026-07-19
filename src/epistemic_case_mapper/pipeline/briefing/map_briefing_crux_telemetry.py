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
    known_claim_ids = _claim_ids(prioritized_map) or _claim_ids(candidate_map)
    known_relation_ids = _relation_ids(prioritized_map) or _relation_ids(candidate_map)
    relation_crux_count = sum(1 for relation in _relations(prioritized_map) if str(relation.get("relation_type")) == "crux_for")
    rows = [
        _score_crux(
            row,
            claim_text,
            briefing_text,
            known_claim_ids=known_claim_ids,
            known_relation_ids=known_relation_ids,
        )
        for row in cruxes
    ]
    concrete_count = sum(1 for row in rows if row["concrete"])
    decision_changing_count = sum(1 for row in rows if row["decision_changing"])
    anchored_count = sum(1 for row in rows if row["anchored_to_map"])
    explicit_claim_anchor_count = sum(1 for row in rows if row["explicit_claim_anchor"])
    explicit_relation_anchor_count = sum(1 for row in rows if row["explicit_relation_anchor"])
    weak_text_anchor_count = sum(1 for row in rows if row["weak_text_anchor"] and not row["explicit_anchor"])
    invalid_reference_count = sum(int(row["invalid_reference_count"]) for row in rows)
    generic_count = sum(1 for row in rows if row["generic"])
    count = len(rows)
    score = 100
    if count == 0:
        score = 30 if relation_crux_count else 20
    else:
        score -= max(0, 2 - concrete_count) * 18
        score -= max(0, 2 - decision_changing_count) * 16
        score -= max(0, 1 - anchored_count) * 14
        score -= max(0, min(2, count) - explicit_claim_anchor_count - explicit_relation_anchor_count) * 10
        score -= invalid_reference_count * 8
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
        "explicit_claim_anchor_count": explicit_claim_anchor_count,
        "explicit_relation_anchor_count": explicit_relation_anchor_count,
        "weak_text_anchor_count": weak_text_anchor_count,
        "invalid_reference_count": invalid_reference_count,
        "generic_crux_count": generic_count,
        "crux_rows": rows,
        "recommended_intervention": _recommended_intervention(
            status,
            generic_count,
            anchored_count,
            decision_changing_count,
            explicit_claim_anchor_count + explicit_relation_anchor_count,
            invalid_reference_count,
        ),
    }


def _crux_rows(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    rows = [row for row in synthesis.get("cruxes", []) if isinstance(row, dict)]
    if rows:
        return rows
    contract = scaffold.get("crux_contract", {}) if isinstance(scaffold.get("crux_contract"), dict) else {}
    return [row for row in contract.get("cruxes", []) if isinstance(row, dict)]


def _score_crux(
    row: dict[str, Any],
    claim_text: str,
    briefing_text: str,
    *,
    known_claim_ids: set[str],
    known_relation_ids: set[str],
) -> dict[str, Any]:
    crux = str(row.get("crux") or row.get("candidate_crux") or "").strip()
    current = str(row.get("current_read", "")).strip()
    would_change = str(row.get("would_change_if", "")).strip()
    why = str(row.get("why_it_matters", "")).strip()
    combined = " ".join((crux, current, would_change, why))
    terms = _content_terms(combined)
    concrete = len(_content_terms(crux)) >= 3 and not _generic_crux(crux)
    decision_changing = _decision_changing(combined)
    supporting_claim_ids = _string_set(row.get("supporting_claim_ids"))
    challenging_claim_ids = _string_set(row.get("challenging_claim_ids"))
    relation_ids = _string_set(row.get("relation_ids"))
    claim_reference_ids = supporting_claim_ids | challenging_claim_ids
    explicit_claim_anchor = bool(claim_reference_ids & known_claim_ids)
    explicit_relation_anchor = bool(relation_ids & known_relation_ids)
    invalid_reference_count = len(claim_reference_ids - known_claim_ids) + len(relation_ids - known_relation_ids)
    weak_text_anchor = _term_overlap(terms, _content_terms(claim_text)) >= 2
    briefing_overlap = _term_overlap(_content_terms(crux), _content_terms(briefing_text)) >= 2
    anchored = explicit_claim_anchor or explicit_relation_anchor or weak_text_anchor
    return {
        "crux": crux,
        "concrete": concrete,
        "decision_changing": decision_changing,
        "anchored_to_map": anchored,
        "explicit_anchor": explicit_claim_anchor or explicit_relation_anchor,
        "explicit_claim_anchor": explicit_claim_anchor,
        "explicit_relation_anchor": explicit_relation_anchor,
        "weak_text_anchor": weak_text_anchor,
        "briefing_text_overlap": briefing_overlap,
        "invalid_reference_count": invalid_reference_count,
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


def _recommended_intervention(
    status: str,
    generic_count: int,
    anchored_count: int,
    decision_changing_count: int,
    explicit_anchor_count: int,
    invalid_reference_count: int,
) -> str:
    if invalid_reference_count:
        return "Repair crux provenance so claim and relation references point to known map IDs."
    if explicit_anchor_count < 2:
        return "Prefer cruxes backed by explicit claim IDs or relation IDs over weak text-overlap anchoring."
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


def _claim_ids(candidate_map: dict[str, Any]) -> set[str]:
    return {
        str(claim.get("claim_id", "")).strip()
        for claim in candidate_map.get("claims", [])
        if isinstance(claim, dict) and str(claim.get("claim_id", "")).strip()
    }


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]


def _relation_ids(candidate_map: dict[str, Any]) -> set[str]:
    return {
        str(relation.get("relation_id", "")).strip()
        for relation in candidate_map.get("relations", [])
        if isinstance(relation, dict) and str(relation.get("relation_id", "")).strip()
    }


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _content_terms(text: str) -> list[str]:
    stop = {
        "the", "and", "that", "with", "from", "this", "these", "those", "were", "was", "are", "for", "into",
        "than", "would", "change", "evidence", "decision", "current", "read", "new", "showed",
    }
    return [term for term in re.findall(r"[a-z0-9]{3,}", text.lower()) if term not in stop]


def _term_overlap(left: list[str], right: list[str]) -> int:
    return len(set(left) & set(right))
