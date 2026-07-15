from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def build_evidence_language_contracts(packet: dict[str, Any], interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    source_appraisals = _source_appraisal_lookup(packet, interface)
    evidence_rows = [
        row
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and _is_memo_facing_inventory_item(row)
    ]
    if not evidence_rows:
        evidence_rows = [row for row in _list(packet.get("evidence_items")) if isinstance(row, dict) and _is_memo_facing_inventory_item(row)]
    for index, row in enumerate(evidence_rows, start=1):
        contract = _evidence_language_contract(row, source_appraisals=source_appraisals, index=index)
        if contract:
            rows.append(contract)
    return _dedupe_rows(rows, "contract_id")[:32]


def _source_appraisal_lookup(packet: dict[str, Any], interface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    by_source = _dict(_dict(packet.get("source_appraisal_report")).get("appraisal_by_source_id"))
    for source_id, appraisal in by_source.items():
        if isinstance(appraisal, dict):
            lookup[str(source_id)] = appraisal
    for row in _list(interface.get("source_appraisal_summary")):
        if not isinstance(row, dict):
            continue
        for source_key in _source_keys(row):
            lookup[source_key] = row
    return lookup


def _evidence_language_contract(row: dict[str, Any], *, source_appraisals: dict[str, Any], index: int) -> dict[str, Any]:
    appraisal = _dict(row.get("source_appraisal")) or _merged_source_appraisal_for_row(row, source_appraisals)
    allowed = _dict(row.get("allowed_wording") or appraisal.get("allowed_wording"))
    warnings = _dedupe([*_string_list(row.get("source_use_warnings")), *_string_list(appraisal.get("source_use_warnings"))])
    design = _evidence_design(appraisal, warnings=warnings)
    source_labels = _string_list(row.get("source_labels")) or _string_list(row.get("source_label"))
    source_ids = _source_ids(row)
    if not source_labels and not source_ids:
        return {}
    return _drop_empty(
        {
            "contract_id": f"language_contract_{index:03d}",
            "item_id": row.get("item_id"),
            "source_labels": source_labels,
            "source_ids": source_ids,
            "evidence_design": design,
            "allowed_language": _allowed_verbs(allowed, design=design, warnings=warnings),
            "avoid_language": _avoid_verbs(allowed, warnings=warnings),
            "must_qualify_with": _string_list(allowed.get("must_qualify_with")),
            "calibration_basis": warnings[:5],
            "wording_rule": _language_wording_rule(design, warnings=warnings),
        }
    )


def _merged_source_appraisal_for_row(row: dict[str, Any], source_appraisals: dict[str, Any]) -> dict[str, Any]:
    appraisals = [_dict(source_appraisals.get(source_key)) for source_key in _source_keys(row)]
    appraisals = [appraisal for appraisal in appraisals if appraisal]
    if not appraisals:
        return {}
    return {
        "document_types": _dedupe(value for appraisal in appraisals for value in _string_list(appraisal.get("document_types") or appraisal.get("document_type"))),
        "recommended_uses": _dedupe(value for appraisal in appraisals for value in _string_list(appraisal.get("recommended_uses") or appraisal.get("recommended_use"))),
        "source_use_warnings": _dedupe(value for appraisal in appraisals for value in _string_list(appraisal.get("source_use_warnings"))),
        "allowed_wording": _merged_allowed_wording(appraisals),
    }


def _merged_allowed_wording(appraisals: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_dict(appraisal.get("allowed_wording")) for appraisal in appraisals]
    causal_values = [row.get("causal_language_allowed") for row in rows if "causal_language_allowed" in row]
    return _drop_empty(
        {
            "causal_language_allowed": False if False in causal_values else True if True in causal_values else None,
            "preferred_verbs": _dedupe(value for row in rows for value in _string_list(row.get("preferred_verbs"))),
            "avoid_terms": _dedupe(value for row in rows for value in _string_list(row.get("avoid_terms"))),
            "must_qualify_with": _dedupe(value for row in rows for value in _string_list(row.get("must_qualify_with"))),
        }
    )


def _evidence_design(appraisal: dict[str, Any], *, warnings: list[str]) -> str:
    text = " ".join(
        [
            *warnings,
            *_string_list(appraisal.get("document_types") or appraisal.get("document_type")),
            *_string_list(appraisal.get("recommended_uses") or appraisal.get("recommended_use")),
            str(appraisal.get("evidence_proximity") or ""),
        ]
    ).lower()
    if "guidance" in text or "advisory" in text:
        return "guidance_or_advisory"
    if "association_not_causation" in warnings or "observational" in text or "cohort" in text:
        return "observational"
    if "indirect_endpoint" in warnings or "surrogate" in text:
        return "indirect_endpoint"
    if "evidence_synthesis" in text or "synthesis" in text or "meta" in text or "review" in text:
        return "evidence_synthesis"
    if "trial" in text or "random" in text:
        return "intervention_or_trial"
    return "unspecified"


def _allowed_verbs(allowed: dict[str, Any], *, design: str, warnings: list[str]) -> list[str]:
    explicit = _string_list(allowed.get("preferred_verbs"))
    if explicit:
        return explicit[:6]
    if design == "observational":
        return ["is associated with", "suggests", "is consistent with", "does not clearly show"]
    if design == "guidance_or_advisory":
        return ["recommends", "frames", "contextualizes", "supports applying"]
    if design == "indirect_endpoint":
        return ["changes the measured endpoint", "supports a mechanism", "calibrates plausibility"]
    if design == "intervention_or_trial":
        return ["shows", "estimates", "supports", "finds"]
    if "quality_limit" in warnings:
        return ["suggests", "is weak evidence for", "is consistent with"]
    return ["supports", "suggests", "bounds", "contextualizes"]


def _avoid_verbs(allowed: dict[str, Any], *, warnings: list[str]) -> list[str]:
    avoid = _string_list(allowed.get("avoid_terms"))
    if allowed.get("causal_language_allowed") is False or "association_not_causation" in warnings:
        avoid.extend(["causes", "proves", "demonstrates causally", "establishes causation"])
    if "guidance_not_independent_empirical_evidence" in warnings:
        avoid.extend(["proves", "demonstrates", "independently shows"])
    return _dedupe(avoid)[:8]


def _language_wording_rule(design: str, *, warnings: list[str]) -> str:
    if design == "observational":
        return "Phrase as association or suggestive evidence unless another source supplies causal support."
    if design == "guidance_or_advisory":
        return "Use as guidance or application context, not as independent empirical proof."
    if design == "indirect_endpoint":
        return "Tie the claim to the measured endpoint and avoid treating it as a direct outcome result."
    if "quality_limit" in warnings:
        return "Use qualified confidence language and keep the source-specific limitation visible."
    return "Keep wording no stronger than the source appraisal allows."


def _is_memo_facing_inventory_item(row: dict[str, Any]) -> bool:
    obligation = str(row.get("obligation_level") or "").strip().lower()
    role = str(row.get("role") or "").strip().lower()
    relation = str(row.get("answer_relation") or "").strip().lower()
    if obligation in {"optional_context", "off_question", "not_relevant"}:
        return False
    if role in {"off_question", "excluded"}:
        return False
    if relation in {"off_question", "not_relevant"}:
        return False
    return True


def _source_ids(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(row.get("source_ids")), str(row.get("source_id") or "").strip()])


def _source_keys(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_source_ids(row), *_string_list(row.get("source_labels")), str(row.get("source_label") or "").strip()])


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        marker = str(row.get(key) or "")
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
