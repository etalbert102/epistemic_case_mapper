from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_identity import (
    project_sources_to_ids_for_model,
    source_id_registry_for_model,
)
from epistemic_case_mapper.map_briefing_writer_decision_interface import build_writer_decision_interface


def build_canonical_decision_writer_packet(
    memo_ready_packet: dict[str, Any],
    *,
    writer_interface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile existing analyst judgments into the single synthesis handoff."""

    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    interface = (
        writer_interface
        if isinstance(writer_interface, dict) and writer_interface.get("schema_id") == "writer_decision_interface_v1"
        else build_writer_decision_interface(packet)
    )
    source_trail = _list(packet.get("source_trail"))
    canonical = {
        "schema_id": "canonical_decision_writer_packet_v1",
        "decision_question": packet.get("decision_question"),
        "decision_brief_skeleton": _decision_brief_skeleton(interface),
        "priority_evidence": _priority_evidence(interface),
        "counterweight_dispositions": _counterweight_dispositions(interface),
        "scope_boundaries": _scope_boundaries(interface),
        "decision_cruxes": _decision_cruxes(interface),
        "source_weight_notes": _source_weight_notes(interface),
        "mandatory_retention_checklist": _mandatory_retention_checklist(packet, interface),
        "citation_registry": _citation_registry(source_trail),
    }
    canonical = project_sources_to_ids_for_model(canonical, source_trail)
    canonical["quality_report"] = build_canonical_decision_writer_packet_quality_report(canonical)
    return canonical


def build_canonical_decision_writer_packet_quality_report(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    priority = _list(packet.get("priority_evidence"))
    counterweights = _list(packet.get("counterweight_dispositions"))
    source_notes = _list(packet.get("source_weight_notes"))
    checklist = _list(packet.get("mandatory_retention_checklist"))
    warnings = []
    for key in ("direct_answer", "scope", "confidence", "main_reason", "strongest_counterweight", "counterweight_disposition"):
        if not str(skeleton.get(key) or "").strip():
            warnings.append(f"missing_skeleton_{key}")
    if _looks_generic(skeleton.get("direct_answer")):
        warnings.append("generic_direct_answer")
    if not priority:
        warnings.append("missing_priority_evidence")
    if not counterweights:
        warnings.append("missing_counterweight_dispositions")
    if not source_notes:
        warnings.append("missing_source_weight_notes")
    if not checklist:
        warnings.append("missing_mandatory_retention_checklist")
    if any(not _source_ids(row) for row in [*priority, *counterweights, *source_notes, *checklist] if isinstance(row, dict)):
        warnings.append("source_id_missing_from_canonical_rows")
    return {
        "schema_id": "canonical_decision_writer_packet_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "warnings": _dedupe(warnings),
        "priority_evidence_count": len(priority),
        "counterweight_disposition_count": len(counterweights),
        "source_weight_note_count": len(source_notes),
        "mandatory_retention_count": len(checklist),
    }


def _decision_brief_skeleton(interface: dict[str, Any]) -> dict[str, Any]:
    answer_frame = _dict(interface.get("answer_frame"))
    practical_cards = _list(interface.get("practical_implication_cards"))
    counterweights = _counterweight_dispositions(interface)
    scope = _scope_boundaries(interface)
    cruxes = _decision_cruxes(interface)
    most_important_quantity = _most_important_quantity(interface)
    return _drop_empty(
        {
            "direct_answer": _short_text(answer_frame.get("direct_answer") or interface.get("bottom_line"), 520),
            "scope": _short_text(answer_frame.get("scope_note") or answer_frame.get("scoping_policy"), 520),
            "confidence": answer_frame.get("confidence") or interface.get("confidence"),
            "confidence_basis": _short_text(answer_frame.get("confidence_basis"), 520),
            "main_reason": _short_text(answer_frame.get("main_support"), 520),
            "most_important_quantity": most_important_quantity,
            "strongest_counterweight": _short_text(answer_frame.get("main_counterweight"), 520),
            "counterweight_disposition": counterweights[0].get("disposition") if counterweights else "",
            "exceptions": [_short_text(row.get("statement") or row.get("claim"), 300) for row in scope[:4] if isinstance(row, dict)],
            "decision_crux": _short_text(_first_text(cruxes, keys=("statement", "claim")), 420),
            "practical_implication": _short_text(_first_text(practical_cards, keys=("statement",)), 520)
            or _short_text(answer_frame.get("decision_application"), 520),
        }
    )


def _priority_evidence(interface: dict[str, Any]) -> list[dict[str, Any]]:
    roles = {"strongest_support", "quantitative_anchor", "strongest_counterweight", "scope_boundary", "decision_crux"}
    rows = [_evidence_row(row) for row in _list(interface.get("decision_evidence_table")) if isinstance(row, dict) and row.get("role") in roles]
    return _dedupe_rows(rows, "item_id")[:18]


def _evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "answer_relation": row.get("answer_relation"),
            "memo_function": row.get("memo_function"),
            "claim": _short_text(row.get("claim") or row.get("reader_claim"), 520),
            "source_labels": _string_list(row.get("source_labels")),
            "quantities": _brief_quantities(row),
            "decision_relevance": _short_text(row.get("decision_relevance"), 420),
            "source_appraisal_note": _short_text(row.get("source_appraisal_note"), 260),
            "importance_rank": row.get("importance_rank"),
        }
    )


def _counterweight_dispositions(interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    counterweights = _list(interface.get("counterweights_and_disposition")) or [
        row for row in _list(interface.get("decision_evidence_table")) if isinstance(row, dict) and row.get("role") == "strongest_counterweight"
    ]
    for row in counterweights:
        if not isinstance(row, dict):
            continue
        disposition = _normalized_counterweight_disposition(row)
        rows.append(
            _drop_empty(
                {
                    "item_id": row.get("item_id"),
                    "claim": _short_text(row.get("claim") or row.get("reader_claim"), 520),
                    "disposition": disposition,
                    "disposition_rationale": _short_text(row.get("disposition_rationale") or row.get("decision_relevance"), 420),
                    "source_labels": _string_list(row.get("source_labels")),
                    "quantities": _brief_quantities(row),
                    "uncertainty": "uncertain" if disposition == "creates_unresolved_crux" else "",
                }
            )
        )
    return _dedupe_rows(rows, "item_id")[:8]


def _normalized_counterweight_disposition(row: dict[str, Any]) -> str:
    text = " ".join(
        str(value or "")
        for value in [
            row.get("disposition"),
            row.get("answer_relation"),
            row.get("memo_function"),
            row.get("disposition_rationale"),
            row.get("decision_relevance"),
        ]
    ).lower()
    if "overturn" in text:
        return "overturns_answer"
    if "dose" in text:
        return "bounds_dose"
    if "population" in text or "subgroup" in text or "individual" in text:
        return "bounds_population"
    if "endpoint" in text or "outcome" in text:
        return "bounds_endpoint"
    if "mechanism" in text or "explain" in text:
        return "explains_mechanism"
    if "bound" in text or "scope" in text or "limit" in text:
        return "weakens_confidence"
    if "challenge" in text or "counterweight" in text or "risk" in text:
        return "weakens_confidence"
    return "creates_unresolved_crux"


def _scope_boundaries(interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    contract = _dict(interface.get("decision_boundary_source_contract"))
    for row in _list(contract.get("boundary_obligations")):
        if not isinstance(row, dict) or row.get("boundary_type") == "counterweight_boundary":
            continue
        rows.append(
            _drop_empty(
                {
                    "boundary_id": row.get("boundary_id"),
                    "boundary_type": row.get("boundary_type"),
                    "statement": _short_text(row.get("statement"), 420),
                    "writing_job": row.get("writing_job"),
                    "source_labels": _string_list(row.get("source_labels")),
                    "quantities": _list(row.get("quantities")),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                }
            )
        )
    if rows:
        return rows[:10]
    return [
        _evidence_row(row)
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and row.get("role") == "scope_boundary"
    ][:10]


def _decision_cruxes(interface: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _evidence_row(row)
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and row.get("role") == "decision_crux"
    ][:8]


def _source_weight_notes(interface: dict[str, Any]) -> list[dict[str, Any]]:
    source_cards = {
        _source_key(row): row
        for row in _list(_dict(interface.get("decision_boundary_source_contract")).get("source_use_cards"))
        if isinstance(row, dict)
    }
    notes = []
    for row in _list(interface.get("source_appraisal_summary")):
        if not isinstance(row, dict):
            continue
        source_key = _source_key(row)
        card = source_cards.get(source_key, {})
        note = _drop_empty(
            {
                "source_labels": _string_list(row.get("source_labels")),
                "decision_directness": row.get("decision_directness") or "unspecified",
                "useful_for": _string_list(card.get("use_for") or row.get("recommended_uses")),
                "not_enough_for": _string_list(row.get("source_use_warnings") or row.get("interpretation_caveats")),
                "key_claims": _string_list(card.get("key_claims"))[:3],
                "key_quantities": _string_list(card.get("key_quantities"))[:5],
                "evidence_item_ids": _string_list(card.get("evidence_item_ids"))[:8],
            }
        )
        if note.get("source_labels"):
            notes.append(note)
    return _dedupe_rows(notes, "source_labels")[:16]


def _mandatory_retention_checklist(packet: dict[str, Any], interface: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = required_memo_obligations(packet)
    if obligations:
        return [_mandatory_obligation_row(row) for row in obligations[:24] if isinstance(row, dict)]
    return [
        _mandatory_evidence_row(row)
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and str(row.get("obligation_level") or "") == "must_include"
    ][:24]


def _mandatory_obligation_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "obligation_id": row.get("obligation_id"),
            "obligation_type": row.get("obligation_type"),
            "role": row.get("role"),
            "statement": _short_text(row.get("statement"), 520),
            "prose_instruction": _short_text(row.get("prose_instruction"), 360),
            "source_labels": _string_list(row.get("source_labels")),
            "quantities": _brief_quantities(row),
            "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
        }
    )


def _mandatory_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "statement": _short_text(row.get("claim") or row.get("reader_claim"), 520),
            "source_labels": _string_list(row.get("source_labels")),
            "quantities": _brief_quantities(row),
        }
    )


def _citation_registry(source_trail: list[Any]) -> list[dict[str, Any]]:
    registry = source_id_registry_for_model(source_trail)
    source_by_id = {str(source.get("source_id") or source.get("source_label") or ""): source for source in source_trail if isinstance(source, dict)}
    rows = []
    for row in registry:
        source = source_by_id.get(str(row.get("source_id") or ""), {})
        rows.append(
            _drop_empty(
                {
                    "source_id": row.get("source_id"),
                    "source_label": source.get("source_label"),
                    "source_url": source.get("source_url"),
                }
            )
        )
    return rows


def _most_important_quantity(interface: dict[str, Any]) -> str:
    for row in _list(interface.get("quantity_anchors")):
        if isinstance(row, dict) and str(row.get("value") or "").strip():
            interpretation = str(row.get("interpretation") or "").strip()
            return f"{row.get('value')}: {interpretation}" if interpretation else str(row.get("value"))
    for row in _list(interface.get("decision_evidence_table")):
        quantities = _brief_quantities(row) if isinstance(row, dict) else []
        if quantities:
            first = quantities[0]
            interpretation = str(first.get("interpretation") or "").strip()
            return f"{first.get('value')}: {interpretation}" if interpretation else str(first.get("value"))
    return ""


def _brief_quantities(row: dict[str, Any]) -> list[dict[str, str]]:
    quantities = []
    for quantity in _list(row.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        quantities.append(
            _drop_empty(
                {
                    "value": value,
                    "interpretation": _short_text(quantity.get("interpretation"), 220),
                    "quantity_role": quantity.get("quantity_role"),
                    "source_labels": _string_list(quantity.get("source_labels")),
                }
            )
        )
    return quantities[:6]


def _source_ids(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(row.get("source_ids")), str(row.get("source_id") or "").strip()])


def _source_key(row: dict[str, Any]) -> str:
    return "|".join(_norm(label) for label in _string_list(row.get("source_labels")))


def _first_text(rows: list[Any], *, keys: tuple[str, ...]) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            text = str(row.get(key) or "").strip()
            if text:
                return text
    return ""


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        raw = row.get(key)
        marker = tuple(raw) if isinstance(raw, list) else str(raw or "")
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def _looks_generic(value: Any) -> bool:
    text = _norm(str(value or ""))
    return text in {"state the default answer", "answer the decision question", "not specified"} or len(text.split()) < 5


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
