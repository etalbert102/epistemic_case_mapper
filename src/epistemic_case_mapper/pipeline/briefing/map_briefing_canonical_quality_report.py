from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)


def build_canonical_decision_writer_packet_quality_report(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    classification = _dict(packet.get("decision_answer_classification"))
    priority = _list(packet.get("priority_evidence"))
    counterweights = _list(packet.get("counterweight_dispositions"))
    weighted_lanes = _dict(_dict(packet.get("source_weighted_answer_frame")).get("lanes"))
    source_notes = _list(packet.get("source_weight_notes"))
    language_contracts = _list(packet.get("evidence_language_contracts"))
    source_judgments = _list(packet.get("source_weight_judgments"))
    source_judgment_report = _dict(packet.get("source_weight_judgment_report"))
    source_hierarchy_report = _dict(packet.get("source_hierarchy_report"))
    argument_spine = _dict(packet.get("evidence_weighted_argument_spine"))
    argument_spine_report = _dict(argument_spine.get("quality_report"))
    informative_source_notes = sum(1 for row in source_notes if _informative_source_weight_note(row))
    checklist = _list(packet.get("mandatory_retention_checklist"))
    inventory_items = _inventory_items(_dict(packet.get("organized_evidence_inventory")))
    key_source_fact_count = sum(len(_list(row.get("key_source_facts"))) for row in inventory_items if isinstance(row, dict))
    warnings = _canonical_packet_warnings(
        skeleton=skeleton,
        classification=classification,
        priority=priority,
        weighted_lanes=weighted_lanes,
        counterweights=counterweights,
        source_notes=source_notes,
        informative_source_notes=informative_source_notes,
        source_judgments=source_judgments,
        source_judgment_report=source_judgment_report,
        source_hierarchy_report=source_hierarchy_report,
        checklist=checklist,
        argument_spine=argument_spine,
        argument_spine_report=argument_spine_report,
        inventory_items=inventory_items,
        key_source_fact_count=key_source_fact_count,
        language_contracts=language_contracts,
    )
    return {
        "schema_id": "canonical_decision_writer_packet_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "warnings": _dedupe(warnings),
        "answer_shape": classification.get("answer_shape"),
        "question_option_count": len(_list(classification.get("question_options"))),
        "priority_evidence_count": len(priority),
        "source_weighted_lane_count": len(weighted_lanes),
        "source_weighted_item_count": sum(len(_list(rows)) for rows in weighted_lanes.values()),
        "organized_evidence_count": len(inventory_items),
        "key_source_fact_count": key_source_fact_count,
        "counterweight_disposition_count": len(counterweights),
        "source_weight_note_count": len(source_notes),
        "source_weight_judgment_count": len(source_judgments),
        "source_weight_judgment_status": source_judgment_report.get("status"),
        "source_hierarchy_status": source_hierarchy_report.get("status"),
        "source_hierarchy_primary_driver_source_count": source_hierarchy_report.get("primary_driver_source_count", 0),
        "evidence_language_contract_count": len(language_contracts),
        "argument_spine_step_count": len(_list(argument_spine.get("steps"))),
        "argument_spine_status": argument_spine_report.get("status"),
        "informative_source_weight_note_count": informative_source_notes,
        "mandatory_retention_count": len(checklist),
    }


def _canonical_packet_warnings(**parts: Any) -> list[str]:
    warnings: list[str] = []
    skeleton = _dict(parts["skeleton"])
    warnings.extend(
        f"missing_skeleton_{key}"
        for key in ("direct_answer", "scope", "confidence", "main_reason", "strongest_counterweight", "counterweight_disposition")
        if not str(skeleton.get(key) or "").strip()
    )
    if _looks_generic(skeleton.get("direct_answer")):
        warnings.append("generic_direct_answer")
    if _looks_truncated_or_scaffolded(skeleton.get("direct_answer")):
        warnings.append("truncated_or_scaffolded_direct_answer")
    if _looks_truncated_or_scaffolded(skeleton.get("practical_implication")):
        warnings.append("truncated_or_scaffolded_practical_implication")
    if not str(_dict(parts["classification"]).get("answer_shape") or "").strip():
        warnings.append("missing_decision_answer_classification")
    warnings.extend(_missing_collection_warnings(parts))
    if _dict(parts["source_judgment_report"]).get("status") == "warning":
        warnings.append("source_weight_judgments_warning")
    if _dict(parts["source_hierarchy_report"]).get("status") == "warning":
        warnings.append("source_hierarchy_warning")
    if _dict(parts["argument_spine_report"]).get("status") == "warning":
        warnings.append("argument_spine_warning")
    if _rows_missing_source_ids(parts):
        warnings.append("source_id_missing_from_canonical_rows")
    if parts.get("inventory_items") and not parts.get("key_source_fact_count"):
        warnings.append("key_source_facts_missing_from_canonical_inventory")
    return warnings


def _missing_collection_warnings(parts: dict[str, Any]) -> list[str]:
    checks = (
        ("missing_priority_evidence", parts["priority"]),
        ("missing_source_weighted_answer_frame", parts["weighted_lanes"]),
        ("missing_counterweight_dispositions", parts["counterweights"]),
        ("missing_source_weight_notes", parts["source_notes"]),
        ("missing_source_weight_judgments", parts["source_judgments"]),
        ("missing_mandatory_retention_checklist", parts["checklist"]),
        ("missing_evidence_weighted_argument_spine", _list(_dict(parts["argument_spine"]).get("steps"))),
        ("missing_organized_evidence_inventory", parts["inventory_items"]),
        ("missing_evidence_language_contracts", parts["language_contracts"]),
    )
    warnings = [label for label, rows in checks if not rows]
    if parts["source_notes"] and parts["informative_source_notes"] == 0:
        warnings.append("source_weight_notes_uninformative")
    return warnings


def _rows_missing_source_ids(parts: dict[str, Any]) -> bool:
    public_rows = [*parts["priority"], *parts["counterweights"], *parts["source_notes"], *parts["inventory_items"]]
    if any(not _source_ids(row) for row in public_rows if isinstance(row, dict)):
        return True
    return any(
        _checklist_row_requires_source(row) and not _source_ids(row)
        for row in parts["checklist"]
        if isinstance(row, dict)
    )


def _inventory_items(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for lane_rows in _dict(inventory.get("lanes")).values():
        rows.extend(row for row in _list(lane_rows) if isinstance(row, dict))
    return rows


def _informative_source_weight_note(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("decision_directness") or "").strip() not in {"", "unknown", "unspecified"}:
        return True
    return bool(_list(row.get("useful_for")) or _list(row.get("not_enough_for")) or _list(row.get("key_claims")) or _list(row.get("key_quantities")))


def _source_ids(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(row.get("source_ids")), str(row.get("source_id") or "").strip()])


def _checklist_row_requires_source(row: dict[str, Any]) -> bool:
    role = str(row.get("role") or "").strip().lower()
    if role.endswith("writer_guidance") or role in {"writer_guidance", "critique_writer_guidance"}:
        return False
    return bool(_list(row.get("evidence_item_ids")) or _list(row.get("quantities")) or str(row.get("obligation_type") or "").strip() or str(row.get("claim") or row.get("statement") or "").strip())


def _looks_generic(value: Any) -> bool:
    text = _norm(str(value or ""))
    return text in {"state the default answer", "answer the decision question", "not specified"} or len(text.split()) < 5


def _looks_truncated_or_scaffolded(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return text.endswith(("...", "…")) or "{'classification'" in text or "use the grouped evidence to answer" in lowered or "state the default" in lowered
