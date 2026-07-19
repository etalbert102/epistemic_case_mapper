from __future__ import annotations

import re
from typing import Any


def build_relation_value_ablation_report(*, prioritized_map: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    relations = [row for row in _list(prioritized_map.get("relations")) if isinstance(row, dict)]
    ledger = _dict(scaffold.get("analyst_evidence_ledger"))
    relation_rows = [
        row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("input_kind") or "").startswith("decision_relation")
    ]
    decision_model = _dict(scaffold.get("analyst_decision_model"))
    groups = [row for row in _list(decision_model.get("evidence_groups")) if isinstance(row, dict)]
    relation_group_count = sum(
        1
        for group in groups
        for evidence_id in _list_text(group.get("covered_evidence_item_ids"))
        if evidence_id.startswith("relation:")
    )
    return {
        "schema_id": "relation_value_ablation_report_v1",
        "status": "report_only",
        "graph_relation_count": len(relations),
        "decision_relation_row_count": len(relation_rows),
        "analyst_group_count": len(groups),
        "relation_backed_group_count": relation_group_count,
        "conditions": [
            {"condition": "no_graph", "expected_effect": "relations unavailable; claim-level evidence still available"},
            {"condition": "current_graph", "observed_relation_count": len(relations), "observed_relation_backed_group_count": relation_group_count},
            {"condition": "decision_targeted_relations", "observed_relation_row_count": len(relation_rows)},
        ],
        "recommendation": "keep_relation_stage" if relation_group_count or relation_rows else "do_not_make_relations_memo_obligatory_without_downstream_value",
        "issues": [] if relation_group_count or relation_rows else ["no_observed_relation_value_in_current_artifacts"],
    }


def build_reviewer_effort_ablation_report(*, scaffold: dict[str, Any]) -> dict[str, Any]:
    packet = build_compact_review_packet(scaffold=scaffold)
    locator_count = sum(1 for key in ("source_universe", "strongest_counterweight", "unresolved_cruxes", "quantity_binding") if packet.get(key))
    return {
        "schema_id": "reviewer_effort_ablation_report_v1",
        "status": "ready" if locator_count == 4 else "warning",
        "compact_review_packet_sections": [key for key, value in packet.items() if value and key != "schema_id"],
        "locator_count": locator_count,
        "issues": [] if locator_count == 4 else ["compact_review_packet_missing_locator"],
    }


def build_compact_review_packet(*, scaffold: dict[str, Any]) -> dict[str, Any]:
    model = _dict(scaffold.get("analyst_decision_model"))
    evidence_universe = _dict(scaffold.get("evidence_universe"))
    source_universe = _dict(scaffold.get("source_universe_report"))
    return {
        "schema_id": "compact_review_packet_v1",
        "decision_question": str(scaffold.get("question") or model.get("decision_question") or ""),
        "source_universe": evidence_universe or source_universe,
        "strongest_counterweight": _strongest_counterweight(model),
        "unresolved_cruxes": _list(model.get("cruxes")) or _list_text(model.get("what_would_change_the_answer")),
        "quantity_binding": {
            "quantity_relevance_decisions": _list(model.get("quantity_relevance_decisions"))[:20],
            "known_result_tuple_count": _dict(scaffold.get("analyst_decision_model_verification_report")).get("known_result_tuple_count", 0),
        },
        "readiness": {
            "analyst_verifier": _dict(scaffold.get("analyst_decision_model_verification_report")).get("status"),
            "evidence_accounting": _dict(scaffold.get("evidence_accounting_report")).get("status"),
            "packet_quality": _dict(scaffold.get("packet_quality_gate_report")).get("status"),
        },
    }


def build_adversarial_memo_qa_report(*, memo_markdown: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    memo = str(memo_markdown or "")
    active_sources = set(_list_text(_dict(scaffold.get("active_cited_source_report")).get("active_source_ids")))
    cited_source_ids = set(re.findall(r"\[([a-zA-Z0-9_.:-]+)\]", memo))
    outside_sources = sorted(source_id for source_id in cited_source_ids if active_sources and source_id not in active_sources)
    model = _dict(scaffold.get("analyst_decision_model"))
    required_phrases = _list_text(_dict(model.get("decision_logic")).get("do_not_overstate")) + _list_text(model.get("do_not_overstate_constraints"))
    missing_constraints = [phrase for phrase in required_phrases if phrase and phrase.lower() not in memo.lower()]
    quantity_rows = [
        row
        for row in _list(model.get("quantity_relevance_decisions"))
        if isinstance(row, dict) and str(row.get("memo_inclusion") or "") == "must_use"
    ]
    missing_quantities = [
        str(row.get("quantity_value") or "")
        for row in quantity_rows
        if str(row.get("quantity_value") or "") and str(row.get("quantity_value") or "") not in memo
    ]
    warnings = [
        *(["source_outside_active_universe"] if outside_sources else []),
        *(["do_not_overstate_constraint_not_visible"] if missing_constraints else []),
        *(["must_use_quantity_not_visible"] if missing_quantities else []),
    ]
    return {
        "schema_id": "adversarial_memo_qa_report_v1",
        "status": "report_only_ready" if not warnings else "report_only_warning",
        "warnings": warnings,
        "source_ids_outside_active_universe": outside_sources,
        "missing_do_not_overstate_constraints": missing_constraints,
        "missing_must_use_quantities": missing_quantities,
        "checks": [
            "source_outside_active_universe",
            "do_not_overstate_constraint_visibility",
            "must_use_quantity_visibility",
            "internal_id_leakage",
        ],
    }


def build_memo_mutation_eval(*, memo_markdown: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    baseline = build_adversarial_memo_qa_report(memo_markdown=memo_markdown, scaffold=scaffold)
    active_sources = _list_text(_dict(scaffold.get("active_cited_source_report")).get("active_source_ids"))
    mutations = []
    if active_sources:
        mutated = str(memo_markdown or "") + "\n\n[mutated_source_outside_universe]\n"
        report = build_adversarial_memo_qa_report(memo_markdown=mutated, scaffold=scaffold)
        mutations.append({"mutation": "inject_outside_source_citation", "detected": "source_outside_active_universe" in report["warnings"]})
    return {
        "schema_id": "memo_mutation_eval_v1",
        "status": "ready" if all(row["detected"] for row in mutations) else "warning",
        "baseline_status": baseline["status"],
        "mutation_count": len(mutations),
        "detected_mutation_count": sum(1 for row in mutations if row["detected"]),
        "mutations": mutations,
        "issues": [] if all(row["detected"] for row in mutations) else ["undetected_memo_mutation"],
    }


def _strongest_counterweight(model: dict[str, Any]) -> dict[str, Any]:
    counterweights = [row for row in _list(model.get("counterweight_dispositions")) if isinstance(row, dict)]
    if counterweights:
        return counterweights[0]
    logic = _dict(model.get("decision_logic"))
    text = str(logic.get("strongest_counterweight") or "")
    return {"rationale": text} if text else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []
