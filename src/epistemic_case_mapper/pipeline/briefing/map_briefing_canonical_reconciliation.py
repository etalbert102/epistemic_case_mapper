from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)


def reconcile_writer_interface(interface: dict[str, Any], packet: dict[str, Any], balanced_frame: dict[str, Any]) -> dict[str, Any]:
    quantity_truth = _quantity_truth_index(packet)
    limits = _string_list(balanced_frame.get("must_not_overstate"))
    if not quantity_truth and not limits:
        return interface
    updated = dict(interface)
    table = []
    for row in _list(interface.get("decision_evidence_table")):
        if not isinstance(row, dict):
            continue
        table.append(_reconcile_writer_row(row, quantity_truth=quantity_truth, limits=limits))
    if table:
        updated["decision_evidence_table"] = table
    for key in (
        "support_that_drives_answer",
        "counterweights_and_disposition",
        "scope_boundaries",
        "decision_cruxes",
        "must_use_evidence",
        "rescued_context_table",
    ):
        if _list(updated.get(key)):
            updated[key] = [
                _reconcile_writer_row(row, quantity_truth=quantity_truth, limits=limits) if isinstance(row, dict) else row
                for row in _list(updated.get(key))
            ]
    if quantity_truth:
        updated["quantity_anchors"] = _reconcile_quantity_anchors(_list(updated.get("quantity_anchors")), quantity_truth)
    return updated


def reconcile_packet_evidence_items(packet: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
    evidence_items = _list(packet.get("evidence_items"))
    if not evidence_items:
        return packet
    reconciled_by_id = _interface_evidence_by_id(interface)
    updated_items = []
    changed = False
    for item in evidence_items:
        if not isinstance(item, dict):
            updated_items.append(item)
            continue
        item_id = str(item.get("item_id") or "").strip()
        reconciled = reconciled_by_id.get(item_id)
        if not reconciled:
            updated_items.append(item)
            continue
        merged = dict(item)
        for key in (
            "role",
            "reader_evidence_role",
            "answer_relation",
            "memo_function",
            "obligation_level",
            "must_use",
            "quantities",
            "claim_calibration_notes",
            "overstatement_conflict",
            "demotion_reason",
        ):
            if key in reconciled:
                merged[key] = reconciled[key]
        updated_items.append(merged)
        changed = True
    if not changed:
        return packet
    updated_packet = dict(packet)
    updated_packet["evidence_items"] = updated_items
    return updated_packet


def _reconcile_quantity_anchors(anchors: list[Any], quantity_truth: dict[tuple[str, str], dict[str, Any]]) -> list[Any]:
    reconciled = []
    for anchor in anchors:
        if not isinstance(anchor, dict):
            reconciled.append(anchor)
            continue
        value = str(anchor.get("value") or "").strip()
        evidence_ids = _dedupe(
            [
                str(anchor.get("evidence_item_id") or "").strip(),
                str(anchor.get("source_evidence_item_id") or "").strip(),
                str(anchor.get("quantity_id") or "").strip(),
                *_string_list(anchor.get("evidence_item_ids")),
            ]
        )
        truth = _quantity_truth_for(value, evidence_ids, quantity_truth)
        if not truth:
            reconciled.append(anchor)
            continue
        merged = dict(anchor)
        merged["interpretation"] = truth.get("retention_phrase") or truth.get("interpretation") or anchor.get("interpretation")
        if truth.get("quantity_role"):
            merged["role"] = truth.get("quantity_role")
        if truth.get("candidate_id"):
            merged["quantity_id"] = truth.get("candidate_id")
        if truth.get("source_ids"):
            merged["source_ids"] = truth.get("source_ids")
        reconciled.append(_drop_empty(merged))
    return reconciled


def _reconcile_writer_row(row: dict[str, Any], *, quantity_truth: dict[tuple[str, str], dict[str, Any]], limits: list[str]) -> dict[str, Any]:
    updated = dict(row)
    if quantity_truth:
        updated["quantities"] = _reconciled_quantities(updated, quantity_truth)
    conflict = _overstatement_conflict(updated, limits)
    if conflict:
        notes = _dedupe([*_string_list(updated.get("claim_calibration_notes")), conflict["note"]])
        updated["claim_calibration_notes"] = notes
        updated["overstatement_conflict"] = conflict
        if str(updated.get("role") or "") == "strongest_support":
            updated["role"] = "context_only"
            updated["answer_relation"] = "contextualizes_answer"
            updated["memo_function"] = "context"
            updated["obligation_level"] = "context_only"
            updated["must_use"] = False
            updated["demotion_reason"] = conflict["note"]
    return updated


def _reconciled_quantities(row: dict[str, Any], quantity_truth: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    quantities = []
    item_id = str(row.get("item_id") or "").strip()
    lineage = _dict(row.get("lineage"))
    lineage_ids = _dedupe(
        [
            *_string_list(lineage.get("covered_evidence_item_ids")),
            *_string_list(lineage.get("derived_from_claim_ids")),
            *_string_list(lineage.get("derived_from_evidence_item_ids")),
        ]
    )
    evidence_ids = _dedupe([item_id, *lineage_ids, *_string_list(row.get("evidence_item_ids"))])
    for quantity in _list(row.get("quantities")):
        if not isinstance(quantity, dict):
            quantities.append(quantity)
            continue
        value = str(quantity.get("value") or "").strip()
        quantity_evidence_ids = _dedupe(
            [
                *evidence_ids,
                str(quantity.get("quantity_id") or "").strip(),
                str(quantity.get("source_evidence_item_id") or "").strip(),
                *_string_list(quantity.get("evidence_item_ids")),
            ]
        )
        truth = _quantity_truth_for(value, quantity_evidence_ids, quantity_truth)
        if truth:
            merged = dict(quantity)
            merged["interpretation"] = truth.get("retention_phrase") or truth.get("interpretation") or quantity.get("interpretation")
            if truth.get("quantity_role"):
                merged["quantity_role"] = truth.get("quantity_role")
            if truth.get("candidate_id"):
                merged["quantity_id"] = truth.get("candidate_id")
            if truth.get("source_ids"):
                merged["source_ids"] = truth.get("source_ids")
            quantities.append(_drop_empty(merged))
        else:
            quantities.append(quantity)
    return quantities


def _quantity_truth_for(value: str, evidence_ids: list[str], quantity_truth: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    value_key = _quantity_value_key(value)
    for evidence_id in evidence_ids:
        truth = quantity_truth.get((str(evidence_id or "").strip(), value_key))
        if truth:
            return truth
    return {}


def _quantity_truth_index(packet: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    report = _dict(packet.get("analyst_quantity_binding_report"))
    rows = []
    for key in ("must_retain_bindings", "approved_bindings", "candidate_bindings"):
        rows.extend(row for row in _list(report.get(key)) if isinstance(row, dict))
    truth: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if str(row.get("memo_use") or "yes").lower() not in {"yes", "use", "must_use"}:
            continue
        value_key = _quantity_value_key(row.get("value"))
        if not value_key:
            continue
        evidence_ids = _dedupe(
            [
                str(row.get("candidate_id") or "").strip(),
                str(row.get("source_evidence_item_id") or "").strip(),
                *_string_list(row.get("evidence_item_ids")),
            ]
        )
        if not evidence_ids:
            continue
        truth_row = _drop_empty(
            {
                "candidate_id": row.get("candidate_id"),
                "interpretation": row.get("interpretation") or row.get("claim_quantity_interpretation"),
                "retention_phrase": row.get("retention_phrase"),
                "quantity_role": row.get("quantity_role") or row.get("claim_quantity_role"),
                "source_ids": _string_list(row.get("source_ids")),
            }
        )
        for evidence_id in evidence_ids:
            truth[(evidence_id, value_key)] = truth_row
    _index_quantity_truth_by_packet_items(packet, truth)
    return truth


def _index_quantity_truth_by_packet_items(packet: dict[str, Any], truth: dict[tuple[str, str], dict[str, Any]]) -> None:
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        item_ids = _dedupe(
            [
                str(item.get("item_id") or "").strip(),
                *_string_list(item.get("evidence_item_ids")),
                *_string_list(_dict(item.get("lineage")).get("derived_from_claim_ids")),
                *_string_list(_dict(item.get("lineage")).get("covered_evidence_item_ids")),
            ]
        )
        if not item_ids:
            continue
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value_key = _quantity_value_key(quantity.get("value"))
            if not value_key:
                continue
            existing = _quantity_truth_for(
                str(quantity.get("value") or ""),
                _dedupe(
                    [
                        str(quantity.get("quantity_id") or "").strip(),
                        str(quantity.get("source_evidence_item_id") or "").strip(),
                        *_string_list(quantity.get("evidence_item_ids")),
                        *item_ids,
                    ]
                ),
                truth,
            )
            if not existing:
                continue
            for item_id in item_ids:
                truth[(item_id, value_key)] = existing


def _quantity_value_key(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def _overstatement_conflict(row: dict[str, Any], limits: list[str]) -> dict[str, str]:
    claim = _norm(row.get("claim") or row.get("reader_claim") or "")
    if not claim or str(row.get("role") or "") != "strongest_support":
        return {}
    for limit in limits:
        limit_text = _norm(limit)
        if not limit_text:
            continue
        overlap = _content_token_overlap(claim, limit_text)
        if overlap >= 2 and _has_limit_action(limit_text):
            return {
                "limit": str(limit),
                "note": "Demoted from load-bearing support because it overlaps an explicit overstatement limit.",
            }
    return {}


def _content_token_overlap(left: str, right: str) -> int:
    stop = {
        "the",
        "and",
        "or",
        "not",
        "claim",
        "based",
        "evidence",
        "limited",
        "support",
        "supports",
        "because",
        "with",
        "from",
        "that",
        "this",
    }
    left_tokens = {token for token in left.split() if len(token) >= 5 and token not in stop}
    right_tokens = {token for token in right.split() if len(token) >= 5 and token not in stop}
    return len(left_tokens & right_tokens)


def _has_limit_action(text: str) -> bool:
    return any(token in text for token in ("do not", "avoid", "must not", "should not", "overstate", "cannot"))


def _interface_evidence_by_id(interface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in _list(interface.get("decision_evidence_table")):
        if isinstance(row, dict) and row.get("item_id"):
            rows[str(row.get("item_id"))] = row
    return rows


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
