from __future__ import annotations

from copy import deepcopy
from typing import Any


def adjudicate_packet_roles(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = deepcopy(packet if isinstance(packet, dict) else {})
    answer = packet.get("answer_frame") if isinstance(packet.get("answer_frame"), dict) else {}
    answer_text = " ".join(str(answer.get(key) or "") for key in ("default_answer", "classification", "scope")).lower()
    candidates = []
    applied = []
    for bundle in packet.get("evidence_bundles", []) if isinstance(packet.get("evidence_bundles"), list) else []:
        if not isinstance(bundle, dict):
            continue
        current_role = str(bundle.get("decision_role") or "context")
        claim = str(bundle.get("claim") or "")
        recommended, reason = _recommended_role(current_role, claim, answer_text)
        if not recommended or recommended == current_role:
            continue
        candidate = {
            "bundle_id": bundle.get("bundle_id"),
            "current_role": current_role,
            "recommended_role": recommended,
            "reason": reason,
            "claim": claim,
            "confidence": "high",
        }
        candidates.append(candidate)
        bundle["decision_role"] = recommended
        bundle["role_adjudicated_from"] = current_role
        bundle["role_adjudication_reason"] = reason
        bundle["directionality"] = _directionality_for_role(recommended)
        bundle["section_use"] = _section_use_for_role(recommended)
        bundle["section_targets"] = _section_targets_for_role(recommended)
        applied.append(candidate)
    return packet, {
        "schema_id": "packet_role_adjudication_report_v1",
        "status": "changed" if applied else "unchanged",
        "method": "high_confidence_generic_role_conflict_rules",
        "candidate_count": len(candidates),
        "applied_count": len(applied),
        "role_conflict_candidates": candidates,
        "applied_role_updates": applied,
    }


def _recommended_role(current_role: str, claim: str, answer_text: str) -> tuple[str, str]:
    lowered = claim.lower()
    if current_role == "counterweight" and _supports_neutral_default(lowered, answer_text):
        return "strongest_support", "no-association or low-concern evidence supports the neutral/default answer frame"
    if current_role == "counterweight" and _scope_limited_claim(lowered) and not _global_harm_claim(lowered):
        return "scope_boundary", "claim mainly bounds applicability to a subgroup or condition"
    if current_role == "strongest_support" and _contrary_claim(lowered):
        return "counterweight", "claim describes failure, worse outcomes, or adverse evidence"
    if current_role == "strongest_support" and _scope_limited_claim(lowered):
        return "scope_boundary", "support claim is mainly conditional or scope-limited"
    return "", ""


def _supports_neutral_default(claim: str, answer_text: str) -> bool:
    neutral_answer = any(term in answer_text for term in ("neutral", "not associated", "low concern", "does not", "no clear", "mixed"))
    no_adverse_association = any(
        term in claim
        for term in (
            "not associated",
            "no association",
            "does not appear",
            "does not show",
            "not linked",
            "lack of evidence linking",
            "not generally supported",
        )
    )
    return neutral_answer and no_adverse_association


def _scope_limited_claim(claim: str) -> bool:
    return any(
        term in claim
        for term in (
            "only applies",
            "does not hold for",
            "subgroup",
            "individuals with",
            "people with",
            "participants with",
            "where ",
            "when ",
            "unless ",
        )
    )


def _global_harm_claim(claim: str) -> bool:
    return any(term in claim for term in ("all-cause", "overall", "general population", "dose-response"))


def _contrary_claim(claim: str) -> bool:
    if any(
        term in claim
        for term in ("not associated", "no association", "unlikely to adversely", "does not show", "does not appear")
    ):
        return False
    return any(
        term in claim
        for term in (
            "failed",
            "failure",
            "higher risk",
            "increased risk",
            "worse",
            "adverse",
            "challenge",
            "contrary",
        )
    )


def _directionality_for_role(role: str) -> str:
    return {
        "strongest_support": "supports",
        "counterweight": "challenges",
        "scope_boundary": "scopes",
        "decision_crux": "in_tension",
        "quantitative_anchor": "quantifies",
        "mechanism": "explains_or_proxies",
    }.get(role, "contextualizes")


def _section_use_for_role(role: str) -> str:
    return {
        "strongest_support": "Use as load-bearing support for the current read.",
        "counterweight": "Use as the strongest contrary or limiting evidence.",
        "scope_boundary": "Use to bound where the answer travels.",
        "decision_crux": "Use to state what would change the answer.",
        "quantitative_anchor": "Use as a concrete numerical anchor.",
        "mechanism": "Use as mechanism or proxy evidence without over-weighting it.",
    }.get(role, "Use only as context if it clarifies the decision.")


def _section_targets_for_role(role: str) -> list[str]:
    if role in {"strongest_support", "quantitative_anchor", "mechanism"}:
        return ["Evidence Carrying the Conclusion"]
    if role == "counterweight":
        return ["Why This Read", "Decision Cruxes"]
    if role == "scope_boundary":
        return ["Practical Scope and Exceptions"]
    if role == "decision_crux":
        return ["Decision Cruxes"]
    return ["Why This Read"]
