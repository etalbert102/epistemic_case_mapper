from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


GENERIC_JUDGMENT_PATTERNS = (
    "use counterweights to bound",
    "connect this reasoning step",
    "write directly from",
    "answer the decision question",
    "if they do not overturn",
)


def build_writer_decision_interface(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    """Compile a memo-ready packet into the only context the writer model should see."""

    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    visible_items = _model_visible_evidence_items(packet)
    filtered_items = _filtered_evidence_items(packet, visible_items)
    obligations = required_memo_obligations(packet)
    interface = {
        "schema_id": "writer_decision_interface_v1",
        "decision_question": packet.get("decision_question"),
        "bottom_line": _bottom_line(packet, visible_items),
        "confidence": _dict(packet.get("answer_spine")).get("confidence", "not_specified"),
        "support_that_drives_answer": _evidence_group(visible_items, roles={"strongest_support", "quantitative_anchor"}),
        "counterweights_and_disposition": _counterweights(packet, visible_items),
        "scope_boundaries": _evidence_group(visible_items, roles={"scope_boundary"}),
        "decision_cruxes": _evidence_group(visible_items, roles={"decision_crux"}),
        "practical_implications": _practical_implications(packet, visible_items),
        "must_use_evidence": [_writer_evidence_item(item) for item in visible_items],
        "quantity_anchors": _quantity_anchors(visible_items),
        "source_trail": _visible_source_trail(packet, visible_items),
        "retention_checklist": _retention_checklist(obligations),
        "excluded_evidence_log": [_excluded_evidence_log_row(item) for item in filtered_items],
        "lineage_report": _lineage_report(packet, visible_items, filtered_items, obligations),
    }
    quality = build_writer_decision_interface_quality_report(interface)
    interface["quality_warnings"] = quality["warnings"]
    return interface


def build_writer_decision_interface_quality_report(interface: dict[str, Any]) -> dict[str, Any]:
    warnings = []
    if not _list(interface.get("support_that_drives_answer")):
        warnings.append("missing_support_that_drives_answer")
    if not _list(interface.get("counterweights_and_disposition")):
        warnings.append("missing_counterweights")
    if not _list(interface.get("quantity_anchors")):
        warnings.append("missing_quantity_anchors")
    if _contains_generic_judgment(interface):
        warnings.append("generic_or_scaffolded_judgment_present")
    retention = _list(interface.get("retention_checklist"))
    evidence_ids = {
        evidence_id
        for item in _list(interface.get("must_use_evidence"))
        if isinstance(item, dict)
        for evidence_id in _string_list(item.get("item_id"))
    }
    missing_obligation_evidence = [
        row.get("obligation_id")
        for row in retention
        if isinstance(row, dict)
        and not any(evidence_id in evidence_ids for evidence_id in _string_list(row.get("evidence_item_ids")))
    ]
    if missing_obligation_evidence:
        warnings.append("retention_obligation_without_visible_evidence")
    return {
        "schema_id": "writer_decision_interface_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "warnings": warnings,
        "must_use_evidence_count": len(_list(interface.get("must_use_evidence"))),
        "quantity_anchor_count": len(_list(interface.get("quantity_anchors"))),
        "excluded_evidence_count": len(_list(interface.get("excluded_evidence_log"))),
        "missing_obligation_evidence": missing_obligation_evidence,
    }


def _bottom_line(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> str:
    spine = _dict(packet.get("answer_spine"))
    logic = _dict(packet.get("analyst_decision_logic"))
    for value in (spine.get("default_read"), spine.get("bounded_answer"), logic.get("bounded_bottom_line")):
        text = _clean_answer_text(value)
        if text:
            return text
    support = _first_claim(visible_items, {"strongest_support", "quantitative_anchor"})
    counter = _first_claim(visible_items, {"strongest_counterweight"})
    if support and counter:
        return f"{support} The main counterweight is: {counter}"
    return support or counter


def _counterweights(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weighting = _dict(packet.get("analyst_decision_logic")).get("counterweight_weighting")
    rows = []
    for item in visible_items:
        if not isinstance(item, dict) or str(item.get("role") or "") != "strongest_counterweight":
            continue
        row = _writer_evidence_item(item)
        row["disposition"] = _counterweight_disposition(weighting)
        row["disposition_rationale"] = _short_text(str(weighting or ""), 320)
        rows.append(row)
    return rows


def _counterweight_disposition(weighting: Any) -> str:
    text = str(weighting or "").lower()
    if "overturn" in text or "change" in text:
        return "bounds_or_may_change"
    if "weaken" in text:
        return "weakens"
    if "bound" in text or "scope" in text or "limit" in text:
        return "bounds"
    return "requires_adjudication"


def _practical_implications(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[str]:
    logic = _dict(packet.get("analyst_decision_logic"))
    rows = _string_list(logic.get("practical_implications"))
    if rows:
        return rows[:5]
    bottom = _bottom_line(packet, visible_items)
    return [_short_text(f"Act on the bounded answer while respecting the listed counterweights and scope boundaries: {bottom}", 420)] if bottom else []


def _evidence_group(visible_items: list[dict[str, Any]], *, roles: set[str]) -> list[dict[str, Any]]:
    return [_writer_evidence_item(item) for item in visible_items if isinstance(item, dict) and str(item.get("role") or "") in roles]


def _writer_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "role": item.get("role"),
        "claim": item.get("reader_claim"),
        "source_labels": _source_labels(item),
        "quantities": _quantity_values(item.get("quantities")),
        "decision_relevance": _short_text(str(item.get("decision_relevance") or ""), 360),
        "caveat": _short_text(str(item.get("caveat") or ""), 260),
        "lineage": _dict(item.get("lineage")),
        "obligation_level": item.get("obligation_level"),
        "memo_function": item.get("memo_function"),
    }


def _quantity_anchors(visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in visible_items:
        if not isinstance(item, dict):
            continue
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value:
                continue
            rows.append(
                {
                    "value": value,
                    "interpretation": str(quantity.get("interpretation") or "").strip(),
                    "source_labels": _source_labels(quantity) or _source_labels(item),
                    "evidence_item_id": item.get("item_id"),
                    "role": item.get("role"),
                }
            )
    return rows


def _visible_source_trail(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_labels = {label for item in visible_items for label in _source_labels(item)}
    rows = []
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or source.get("display_label") or "").strip()
        if label and label in visible_labels:
            rows.append(source)
    if rows:
        return rows
    return [{"source_label": label} for label in sorted(visible_labels)]


def _retention_checklist(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for obligation in obligations:
        rows.append(
            {
                "obligation_id": obligation.get("obligation_id"),
                "obligation_type": obligation.get("obligation_type"),
                "role": obligation.get("role"),
                "statement": obligation.get("statement"),
                "prose_instruction": obligation.get("prose_instruction"),
                "source_labels": _string_list(obligation.get("source_labels")),
                "quantities": _quantity_values(obligation.get("quantities")),
                "evidence_item_ids": _string_list(obligation.get("evidence_item_ids")),
            }
        )
    return rows


def _excluded_evidence_log_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "role": item.get("role"),
        "source_label": item.get("source_label"),
        "obligation_level": item.get("obligation_level"),
        "must_use": bool(item.get("must_use")),
        "filter_reason": "not_marked_must_use_for_memo_synthesis",
    }


def _lineage_report(
    packet: dict[str, Any],
    visible_items: list[dict[str, Any]],
    filtered_items: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_id": "writer_decision_interface_lineage_report_v1",
        "source_packet_schema_id": packet.get("schema_id"),
        "source_packet_method": packet.get("method"),
        "original_evidence_item_count": len([item for item in _list(packet.get("evidence_items")) if isinstance(item, dict)]),
        "model_visible_evidence_item_count": len(visible_items),
        "filtered_evidence_item_count": len(filtered_items),
        "required_obligation_count": len(obligations),
        "visible_evidence_item_ids": [str(item.get("item_id") or "") for item in visible_items],
        "filtered_evidence_item_ids": [str(item.get("item_id") or "") for item in filtered_items],
        "judgment_sources": [
            "answer_spine",
            "analyst_decision_logic",
            "memo_obligations",
            "analyst_quantity_binding_report",
        ],
    }


def _model_visible_evidence_items(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict) and _evidence_item_model_visible(item)
    ]


def _filtered_evidence_items(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_ids = {str(item.get("item_id") or "") for item in visible_items if isinstance(item, dict)}
    return [
        item
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict) and str(item.get("item_id") or "") not in visible_ids
    ]


def _evidence_item_model_visible(item: dict[str, Any]) -> bool:
    return bool(item.get("must_use")) or str(item.get("obligation_level") or "") == "must_include"


def _contains_generic_judgment(value: Any) -> bool:
    text = str(value or "").lower()
    if any(pattern in text for pattern in GENERIC_JUDGMENT_PATTERNS):
        return True
    if isinstance(value, dict):
        return any(_contains_generic_judgment(row) for row in value.values())
    if isinstance(value, list):
        return any(_contains_generic_judgment(row) for row in value)
    return False


def _first_claim(visible_items: list[dict[str, Any]], roles: set[str]) -> str:
    for item in visible_items:
        if isinstance(item, dict) and str(item.get("role") or "") in roles:
            claim = str(item.get("reader_claim") or "").strip()
            if claim:
                return claim
    return ""


def _clean_answer_text(value: Any) -> str:
    text = _short_text(str(value or ""), 700)
    text = re.sub(r"^The evidence supports a bounded answer to ['\"][^'\"]+['\"]:\s*", "", text)
    text = re.sub(r"^The evidence supports a bounded answer:\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _source_labels(item: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(item.get("source_labels")), str(item.get("source_label") or "").strip()])


def _quantity_values(value: Any) -> list[dict[str, str]]:
    rows = []
    for row in _list(value):
        if isinstance(row, dict):
            quantity = str(row.get("value") or "").strip()
            interpretation = str(row.get("interpretation") or "").strip()
        else:
            quantity = str(row or "").strip()
            interpretation = ""
        if quantity:
            rows.append({"value": quantity, "interpretation": interpretation})
    return rows
