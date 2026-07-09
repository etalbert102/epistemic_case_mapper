from __future__ import annotations

from copy import deepcopy
from typing import Any


_ROLE_DIRECTIONALITY = {
    "strongest_support": "supports",
    "counterweight": "challenges",
    "scope_boundary": "scopes",
    "decision_crux": "in_tension",
    "quantitative_anchor": "quantifies",
    "mechanism": "explains_or_proxies",
}


def adjudicate_packet_roles(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = deepcopy(packet if isinstance(packet, dict) else {})
    candidates = []
    for bundle in packet.get("evidence_bundles", []) if isinstance(packet.get("evidence_bundles"), list) else []:
        if not isinstance(bundle, dict):
            continue
        current_role = str(bundle.get("decision_role") or "context")
        current_directionality = str(bundle.get("directionality") or "")
        expected_directionality = _ROLE_DIRECTIONALITY.get(current_role, "contextualizes")
        explicit_conflicts = _explicit_role_conflicts(bundle, current_role)
        directionality_mismatch = (
            bool(current_directionality)
            and current_role in _ROLE_DIRECTIONALITY
            and current_directionality != expected_directionality
        )
        if not explicit_conflicts and not directionality_mismatch:
            continue
        candidates.append(
            {
                "bundle_id": bundle.get("bundle_id"),
                "current_role": current_role,
                "current_directionality": current_directionality,
                "expected_directionality_for_current_role": expected_directionality,
                "reason": "explicit packet metadata is internally inconsistent",
                "conflict_types": [
                    *explicit_conflicts,
                    *(["role_directionality_contract_mismatch"] if directionality_mismatch else []),
                ],
                "claim": str(bundle.get("claim") or ""),
                "confidence": "metadata_contract",
            }
        )
    return packet, {
        "schema_id": "packet_role_adjudication_report_v1",
        "status": "report_only_warning" if candidates else "unchanged",
        "method": "report_only_explicit_metadata_contract_checks_no_semantic_mutation",
        "candidate_count": len(candidates),
        "applied_count": 0,
        "role_conflict_candidates": candidates,
        "applied_role_updates": [],
        "semantic_boundary": "deterministic code checks explicit packet metadata consistency but does not infer or recommend semantic roles from text",
    }


def _explicit_role_conflicts(bundle: dict[str, Any], current_role: str) -> list[str]:
    labels = {
        str(value).strip()
        for key in ("evidence_role", "claim_type", "decision_function", "source_card_role")
        for value in _listify(bundle.get(key))
        if str(value).strip()
    }
    roles = {current_role, *labels}
    if roles & {"strongest_support", "support"} and roles & {"counterweight", "challenge", "contrary"}:
        return ["explicit_support_counterweight_label_conflict"]
    if roles & {"scope_boundary", "scope", "boundary"} and roles & {"decision_crux", "crux"}:
        return ["explicit_scope_crux_label_conflict"]
    return []


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
