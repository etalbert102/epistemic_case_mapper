from __future__ import annotations

import re
from typing import Any


SCOPE_ROLES = {"scope_limit", "external_validity"}
FINDING_ROLES = {"conclusion_support", "crux", "measurement_validity"}


def relation_pair_intent(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_role = str(left.get("role", ""))
    right_role = str(right.get("role", ""))
    cross_source = str(left.get("source_id", "")) != str(right.get("source_id", ""))
    left_scope = _is_scope_claim(left)
    right_scope = _is_scope_claim(right)
    has_crux = "crux" in {left_role, right_role}
    if cross_source and ((left_scope and right_role in FINDING_ROLES) or (right_scope and left_role in FINDING_ROLES)):
        if _is_study_specific_scope(left if left_scope else right):
            return _intent("cross_source_study_scope_to_finding", allowed=("none",))
        if _looks_mechanistic(left if left_scope else right):
            allowed = ("supports", "in_tension_with", "challenges", "crux_for", "none") if has_crux else (
                "supports",
                "in_tension_with",
                "challenges",
                "none",
            )
            return _intent("cross_source_mechanism_scope_to_finding", allowed=allowed)
        allowed = ("refines", "depends_on", "crux_for", "none") if has_crux else ("refines", "depends_on", "none")
        return _intent("cross_source_general_scope_to_finding", allowed=allowed)
    if not cross_source and ((left_scope and right_role in FINDING_ROLES) or (right_scope and left_role in FINDING_ROLES)):
        allowed = ("refines", "depends_on", "crux_for", "none") if has_crux else ("refines", "depends_on", "none")
        return _intent("same_source_scope_to_finding", allowed=allowed)
    if has_crux:
        return _intent("crux_to_decision_claim", allowed=("crux_for", "supports", "in_tension_with", "challenges", "depends_on", "none"))
    if "implementation_constraint" in {left_role, right_role}:
        return _intent("implementation_to_guidance", allowed=("depends_on", "refines", "none"))
    polarity_pair = {_claim_polarity(_claim_text(left)), _claim_polarity(_claim_text(right))}
    if "mixed" not in polarity_pair and len(polarity_pair) > 1:
        return _intent("cross_source_disagreement" if cross_source else "same_source_disagreement", allowed=("in_tension_with", "challenges", "none"))
    if left_role == right_role == "conclusion_support":
        return _intent(
            "cross_source_agreement" if cross_source else "same_source_agreement",
            allowed=("supports", "similar_to", "in_tension_with", "challenges", "none"),
        )
    if _looks_mechanistic(left) or _looks_mechanistic(right):
        return _intent("mechanism_to_outcome", allowed=("supports", "depends_on", "in_tension_with", "none"))
    return _intent("generic_decision_relation", allowed=("supports", "refines", "depends_on", "in_tension_with", "challenges", "crux_for", "similar_to", "none"))


def relation_pair_penalty(left: dict[str, Any], right: dict[str, Any]) -> tuple[int, str]:
    intent = relation_pair_intent(left, right)
    if intent["intent"] == "cross_source_study_scope_to_finding":
        return 30, "cross_source_study_scope_guard"
    return 0, ""


def relation_semantic_rejection_reason(relation: dict[str, Any], packet: dict[str, Any]) -> str:
    endpoints = _endpoint_lookup(packet)
    source = endpoints.get(str(relation.get("source_claim")), {})
    target = endpoints.get(str(relation.get("target_claim")), {})
    relation_type = str(relation.get("relation_type", ""))
    rationale = _normalize(str(relation.get("rationale", "")))
    if not source or not target:
        return "relation_endpoint_missing_from_packet"
    if relation_type in {"refines", "depends_on"} and _cross_source_study_scope_relation(source, target):
        return "cross_source_study_scope_relation"
    intent = relation_pair_intent(source, target)
    if intent.get("intent") == "cross_source_mechanism_scope_to_finding" and relation_type == "refines":
        return "cross_source_mechanism_scope_refines"
    if relation_type == "in_tension_with" and _sounds_supportive(rationale) and not _has_contrast_marker(rationale):
        return "relation_type_rationale_mismatch"
    if relation_type == "supports" and _has_challenge_marker(rationale):
        return "relation_type_rationale_mismatch"
    if relation_type == "supports" and not _has_support_contract(rationale, source, target):
        return "weak_support_contract"
    if relation_type == "challenges" and not _has_challenge_marker(rationale):
        return "missing_challenge_contract"
    if relation_type == "depends_on" and not _has_dependency_marker(rationale):
        return "missing_dependency_contract"
    if relation_type == "refines" and not _has_refinement_marker(rationale):
        return "missing_refinement_contract"
    if relation_type == "crux_for" and not _has_crux_marker(rationale):
        return "missing_crux_contract"
    return ""


def relation_quality_issue_rows(relations: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[dict[str, str]]:
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in claims}
    rows: list[dict[str, str]] = []
    crux_count = sum(1 for relation in relations if relation.get("relation_type") == "crux_for")
    if relations and crux_count > max(3, int(len(relations) * 0.25)):
        rows.append({"severity": "risk", "issue_type": "crux_relation_overuse", "message": f"Accepted {crux_count} crux_for relations among {len(relations)} relations."})
    for relation in relations:
        source = claim_lookup.get(str(relation.get("source_claim")), {})
        target = claim_lookup.get(str(relation.get("target_claim")), {})
        relation_type = str(relation.get("relation_type", ""))
        rationale = _normalize(str(relation.get("rationale", "")))
        if relation_type in {"refines", "depends_on"} and _cross_source_study_scope_relation(source, target):
            rows.append(_relation_issue("risk", "cross_source_study_scope_relation", relation))
        elif relation_type == "in_tension_with" and _sounds_supportive(rationale) and not _has_contrast_marker(rationale):
            rows.append(_relation_issue("risk", "relation_type_rationale_mismatch", relation))
        elif relation_type == "supports" and _has_challenge_marker(rationale):
            rows.append(_relation_issue("risk", "relation_type_rationale_mismatch", relation))
        elif relation_type == "supports" and not _has_support_contract(rationale, source, target):
            rows.append(_relation_issue("risk", "weak_support_contract", relation))
        elif relation_type == "crux_for" and not _has_crux_marker(rationale):
            rows.append(_relation_issue("risk", "weak_crux_relation_contract", relation))
    return rows


def _intent(intent: str, *, allowed: tuple[str, ...]) -> dict[str, Any]:
    return {"intent": intent, "allowed_relation_types": list(allowed)}


def _endpoint_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(packet[side].get("claim_id", "")): packet[side]
        for side in ("left", "right")
        if isinstance(packet.get(side), dict)
    }


def _relation_issue(severity: str, issue_type: str, relation: dict[str, Any]) -> dict[str, str]:
    return {
        "severity": severity,
        "issue_type": issue_type,
        "message": f"{relation.get('relation_id', 'unknown')} has relation_type={relation.get('relation_type')} with a weak or mismatched semantic contract.",
    }


def _cross_source_study_scope_relation(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("source_id", "")) == str(right.get("source_id", "")):
        return False
    return (_is_study_specific_scope(left) and str(right.get("role", "")) in FINDING_ROLES) or (
        _is_study_specific_scope(right) and str(left.get("role", "")) in FINDING_ROLES
    )


def _is_scope_claim(claim: dict[str, Any]) -> bool:
    return str(claim.get("role", "")) in SCOPE_ROLES


def _is_study_specific_scope(claim: dict[str, Any]) -> bool:
    if not _is_scope_claim(claim):
        return False
    text = _normalize(_claim_text(claim))
    return bool(re.search(r"\b(?:study|trial|analysis|participants?|patients?|enrolled|included|excluded|cohort|population|randomized|baseline)\b", text))


def _looks_mechanistic(claim: dict[str, Any]) -> bool:
    text = _normalize(_claim_text(claim))
    return bool(re.search(r"\b(?:mechanism|mediated|driven|biomarkers?|markers?|particles?|pathway|cause|causal|physiological)\b", text))


def _claim_text(claim: dict[str, Any]) -> str:
    return f"{claim.get('claim', '')} {claim.get('excerpt', '')}"


def _claim_polarity(text: str) -> str:
    normalized = f" {_normalize(text)} "
    positive = any(marker in normalized for marker in (" lower risk ", " reduced risk ", " no association ", " not associated ", " no adverse ", " did not have adverse ", " beneficial ", " safely "))
    negative = any(marker in normalized for marker in (" higher risk ", " increased risk ", " harmful ", " adverse effect ", " adverse effects ", " mortality ", " concern "))
    if positive and not negative:
        return "positive_or_null"
    if negative and not positive:
        return "negative_or_concern"
    return "mixed"


def _sounds_supportive(text: str) -> bool:
    return any(marker in text for marker in ("both claims", "consistent", "reinforces", "supports", "aligns with", "independently conclude", "same conclusion"))


def _has_contrast_marker(text: str) -> bool:
    return any(marker in text for marker in ("while", "whereas", "however", "but", "although", "tension", "conflict", "contradict"))


def _has_challenge_marker(text: str) -> bool:
    return any(marker in text for marker in ("challenge", "challenges", "weakens", "undercuts", "contradicts", "casts doubt", "conflicts", "inconsistent"))


def _has_support_contract(text: str, source: dict[str, Any], target: dict[str, Any]) -> bool:
    if _has_mechanism_marker(text) or _has_quantitative_marker(text) or _has_same_proposition_marker(text):
        return True
    source_terms = _support_contract_terms(_claim_text(source))
    target_terms = _support_contract_terms(_claim_text(target))
    return len(source_terms & target_terms) >= 3 and _has_supportive_direction_marker(text)


def _has_same_proposition_marker(text: str) -> bool:
    return any(marker in text for marker in ("same proposition", "same endpoint", "same outcome", "same finding", "same conclusion", "convergent evidence", "independently conclude"))


def _has_mechanism_marker(text: str) -> bool:
    return any(marker in text for marker in ("mechanism", "explains", "because", "driven by", "pathway", "mediated", "basis for", "why "))


def _has_quantitative_marker(text: str) -> bool:
    return bool(re.search(r"\b(?:estimate|effect|risk ratio|relative risk|hazard ratio|odds ratio|confidence interval|ci|subgroup|adjustment|adjusted|statistical|quantitative|dose-response)\b|%|\d", text))


def _has_supportive_direction_marker(text: str) -> bool:
    return any(marker in text for marker in ("supports", "aligns", "consistent", "convergent", "reinforces", "strengthens"))


def _support_contract_terms(text: str) -> set[str]:
    stop = {
        "claim",
        "claims",
        "source",
        "study",
        "studies",
        "evidence",
        "finding",
        "findings",
        "association",
        "associated",
        "consumption",
        "risk",
    }
    return {token for token in re.findall(r"[a-z][a-z0-9_-]{3,}", _normalize(text)) if token not in stop}


def _has_dependency_marker(text: str) -> bool:
    return any(marker in text for marker in ("depends", "only if", "only when", "condition", "contingent", "requires", "under ", "bounded by", "provided that"))


def _has_refinement_marker(text: str) -> bool:
    return any(marker in text for marker in ("refines", "scope", "boundary", "population", "endpoint", "condition", "specific", "limits", "applies", "generalizability"))


def _has_crux_marker(text: str) -> bool:
    if re.search(r"\bif\b.+\b(?:were|was|is)\s+false\b", text):
        return True
    if re.search(r"\bif\b.+\bimplies?\b", text):
        return True
    return any(marker in text for marker in ("crux", "determines", "would change", "changes how", "turns on", "hinges", "critical", "decisive", "whether"))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
