from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import (
    build_canonical_decision_writer_packet,
    build_canonical_decision_writer_packet_quality_report,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.map_briefing_source_appraisal import build_source_appraisal_report
from epistemic_case_mapper.map_briefing_source_weight_judgments import build_source_weight_judgment_report

from test_decision_briefing_packet import _scaffold


def test_memo_ready_packet_includes_canonical_decision_writer_packet() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    canonical = packet["canonical_decision_writer_packet"]

    assert canonical["schema_id"] == "canonical_decision_writer_packet_v1"
    assert canonical["decision_question"] == "Should the city adopt option A for flood protection?"
    assert canonical["decision_brief_skeleton"]["direct_answer"]
    assert canonical["decision_brief_skeleton"]["main_reason"]
    assert canonical["decision_answer_classification"]["answer_shape"]
    assert canonical["analyst_reasoning_frame"]
    assert canonical["balanced_answer_frame"]["schema_id"] == "balanced_answer_frame_v1"
    assert canonical["balanced_answer_frame"]["best_current_read"]
    assert canonical["bluf_contract"]["schema_id"] == "bluf_contract_v1"
    assert canonical["bluf_contract"]["recommended_read"]
    assert canonical["bluf_contract"]["one_sentence_version"]
    assert "must_not_overstate" in canonical["balanced_answer_frame"]
    assert canonical["source_weighted_answer_frame"]["lanes"]
    assert canonical["evidence_weighted_argument_spine"]["schema_id"] == "evidence_weighted_argument_spine_v1"
    assert canonical["source_weight_judgments"]
    assert canonical["source_weight_judgment_report"]["schema_id"] == "source_weight_judgment_report_v1"
    assert canonical["evidence_language_contracts"]
    assert canonical["priority_evidence"]
    assert canonical["organized_evidence_inventory"]["item_count"] == len(packet["evidence_items"])
    assert canonical["counterweight_dispositions"]
    assert canonical["source_weight_notes"]
    assert canonical["mandatory_retention_checklist"]
    assert canonical["citation_registry"]
    assert canonical["quality_report"]["schema_id"] == "canonical_decision_writer_packet_quality_report_v1"
    assert canonical["quality_report"]["answer_shape"] == canonical["decision_answer_classification"]["answer_shape"]
    assert canonical["quality_report"]["source_weighted_lane_count"] >= 1
    assert canonical["quality_report"]["source_weight_judgment_count"] == len(canonical["source_weight_judgments"])
    assert canonical["quality_report"]["evidence_language_contract_count"] == len(canonical["evidence_language_contracts"])
    assert canonical["quality_report"]["argument_spine_step_count"] == len(canonical["evidence_weighted_argument_spine"]["steps"])
    assert all(
        row.get("source_id") or row.get("source_ids")
        for row in canonical["priority_evidence"]
        if row.get("role") in {"strongest_support", "strongest_counterweight", "scope_boundary", "decision_crux"}
    )
    assert canonical["quality_report"]["organized_evidence_count"] == len(packet["evidence_items"])


def test_canonical_packet_front_loads_source_weighted_answer_frame() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    frame = packet["canonical_decision_writer_packet"]["source_weighted_answer_frame"]
    lanes = frame["lanes"]

    assert frame["schema_id"] == "source_weighted_answer_frame_v1"
    assert "Use primary answer drivers" in frame["weighting_thesis"]
    assert lanes["primary_answer_drivers"][0]["source_ids"]
    assert lanes["counterweights_or_tensions"][0]["source_ids"]
    assert lanes["scope_limiters"][0]["source_ids"]
    assert all(row.get("reader_evidence_role") for rows in lanes.values() for row in rows)
    assert "source_labels" not in str(frame)
    assert any("main answer" in move for move in frame["required_weighting_moves"])


def test_canonical_source_weighting_uses_explicit_analyst_hierarchy_over_projected_role() -> None:
    packet = {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": "Should option A be adopted?",
        "answer_spine": {"default_read": "Adopt option A with caution.", "confidence": "medium"},
        "source_trail": [{"source_id": "s1", "source_label": "s1"}],
        "analyst_source_hierarchy": {
            "schema_id": "source_weight_hierarchy_v1",
            "hierarchy_thesis": "The source mainly bounds the answer.",
            "lanes": {
                "counterweight_sources": [
                    {
                        "source_ids": ["s1"],
                        "evidence_item_ids": ["item:1"],
                        "role": "Counterweight source.",
                        "rationale": "This source narrows the answer despite the local support role.",
                    }
                ]
            },
            "source_accounting": [{"source_id": "s1", "primary_lane": "counterweight_sources"}],
        },
        "evidence_items": [
            {
                "item_id": "item:1",
                "role": "strongest_support",
                "answer_relation": "supports_answer",
                "reader_claim": "Local row says option A helps.",
                "source_ids": ["s1"],
                "source_labels": ["s1"],
                "lineage": {"evidence_item_ids": ["item:1"]},
                "must_use": True,
            }
        ],
    }

    canonical = build_canonical_decision_writer_packet(packet)
    lanes = canonical["source_weighted_answer_frame"]["lanes"]
    row = lanes["counterweights_or_tensions"][0]

    assert row["source_weight_basis"] == "analyst_source_hierarchy"
    assert row["source_ids"] == ["s1"]
    assert "analyst source hierarchy" in row["why_this_weight"]
    assert "narrows the answer" in row["why_this_weight"]
    assert "primary_answer_drivers" not in lanes


def test_canonical_packet_builds_balanced_answer_frame_from_existing_judgments() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    frame = packet["canonical_decision_writer_packet"]["balanced_answer_frame"]

    assert frame["schema_id"] == "balanced_answer_frame_v1"
    assert frame["best_current_read"]
    assert frame["main_support"]
    assert frame["main_counterweight"] or frame["scope"]
    assert "underused_balance_evidence" in frame
    assert "overstat" in frame["synthesis_instruction"]


def test_canonical_packet_builds_bluf_contract_from_balanced_frame() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    canonical = packet["canonical_decision_writer_packet"]
    contract = canonical["bluf_contract"]

    assert contract["schema_id"] == "bluf_contract_v1"
    assert contract["recommended_read"] == canonical["balanced_answer_frame"]["best_current_read"]
    assert contract["one_sentence_version"]
    assert contract["one_sentence_version"] == contract["recommended_read"]
    assert "within this scope" not in contract["one_sentence_version"]
    assert "..." not in contract["one_sentence_version"]
    assert any("Answer the decision question" in item for item in contract["writing_contract"])


def test_canonical_packet_exposes_source_weight_judgments_with_source_ids() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    judgments = packet["canonical_decision_writer_packet"]["source_weight_judgments"]

    assert judgments
    assert all(row.get("source_ids") for row in judgments)
    assert all(row.get("main_use") for row in judgments)
    assert all(row.get("why_weight_this_way") for row in judgments)
    assert "to drives answer" not in str(judgments)
    assert "Scaffold assignment" not in str(judgments)
    assert "source_labels" not in str(judgments)


def test_source_weight_report_flags_flattened_hierarchy() -> None:
    source_trail = [{"source_id": f"s{index}"} for index in range(5)]
    judgments = [
        {
            "judgment_id": f"j{index}",
            "source_ids": [f"s{index}"],
            "main_use": "drives_answer",
            "why_weight_this_way": "This source links directly to the decision endpoint and population.",
        }
        for index in range(5)
    ]

    report = build_source_weight_judgment_report(judgments, source_trail)

    assert report["status"] == "warning"
    assert "flattened_source_weight_hierarchy" in report["warnings"]


def test_canonical_packet_uses_analyst_quantity_binding_as_truth() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    item = packet["evidence_items"][0]
    item["quantities"] = [
        {
            "value": "25%",
            "interpretation": "stale amount consumed daily",
            "quantity_id": "quantity_binding_candidate_001",
            "source_evidence_item_id": "c1",
        }
    ]
    packet["analyst_quantity_binding_report"] = {
        "schema_id": "analyst_quantity_binding_report_v1",
        "status": "ready",
        "approved_bindings": [
            {
                "candidate_id": "quantity_binding_candidate_001",
                "source_evidence_item_id": "c1",
                "value": "25%",
                "interpretation": "Percent reduction in flood losses in comparable cities.",
                "retention_phrase": "25% reduction in flood losses",
                "quantity_role": "decision_anchor",
                "memo_use": "yes",
                "source_ids": ["s1"],
            }
        ],
    }

    canonical = build_canonical_decision_writer_packet(packet)
    quantities = [
        quantity
        for row in canonical["priority_evidence"]
        if row.get("item_id") == item["item_id"]
        for quantity in row.get("quantities", [])
    ]

    assert quantities
    assert quantities[0]["interpretation"] == "25% reduction in flood losses"
    assert "stale amount consumed daily" not in str(canonical)


def test_canonical_packet_demotes_support_that_conflicts_with_overstatement_limits() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    item = packet["evidence_items"][0]
    item["reader_claim"] = "Option A is protective and beneficial for the city."
    item["claim"] = item["reader_claim"]
    item["role"] = "strongest_support"
    item["answer_relation"] = "supports_answer"
    item["memo_function"] = "answer_anchor"
    item["must_use"] = True
    item["obligation_level"] = "must_include"
    packet.setdefault("analyst_decision_logic", {})["do_not_overstate"] = [
        "Do not claim Option A is protective or beneficial; evidence only supports reduced flood losses in comparable cities."
    ]

    canonical = build_canonical_decision_writer_packet(packet)
    inventory_items = [
        row
        for rows in canonical["organized_evidence_inventory"]["lanes"].values()
        for row in rows
        if row.get("item_id") == item["item_id"]
    ]

    assert inventory_items
    assert inventory_items[0]["role"] == "context_only"
    assert inventory_items[0]["answer_relation"] == "contextualizes_answer"
    assert "Demoted from load-bearing support" in " ".join(inventory_items[0]["claim_calibration_notes"])
    assert all(item["item_id"] not in row.get("evidence_item_ids", []) for row in canonical["mandatory_retention_checklist"])


def test_canonical_packet_gives_unassigned_sources_contextual_judgments() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    built["decision_briefing_packet"]["source_trail"].append(
        {"source_id": "context_source", "source_label": "Context Source", "source_url": "https://example.test/context"}
    )
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    canonical = packet["canonical_decision_writer_packet"]
    judgments = canonical["source_weight_judgments"]

    context_judgment = next(row for row in judgments if row.get("source_ids") == ["context_source"])
    assert context_judgment["main_use"] == "contextualizes"
    assert context_judgment["omission_reason"]
    assert "No memo-facing evidence item" in context_judgment["why_weight_this_way"]
    assert canonical["source_weight_judgment_report"]["status"] == "ready"
    assert "source_ids_without_weight_judgment" not in canonical["source_weight_judgment_report"]["warnings"]


def test_canonical_packet_builds_evidence_weighted_argument_spine() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    spine = packet["canonical_decision_writer_packet"]["evidence_weighted_argument_spine"]
    jobs = {step["memo_job"] for step in spine["steps"]}

    assert spine["quality_report"]["schema_id"] == "argument_spine_quality_report_v1"
    assert "answer" in jobs
    assert "primary_driver" in jobs
    assert "counterweight_or_boundary" in jobs
    assert spine["section_plan"]
    assert any(step.get("reader_evidence_role") for step in spine["steps"])
    assert all(step.get("primary_section") for step in spine["steps"] if step["memo_job"] != "")
    assert any(row["section"].startswith("Why This Is the Best") for row in spine["section_plan"])
    assert spine["quality_report"]["step_count"] == len(spine["steps"])
    assert "source_labels" not in str(spine)


def test_canonical_quality_allows_source_free_writer_guidance() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    canonical = packet["canonical_decision_writer_packet"]
    canonical["mandatory_retention_checklist"].append(
        {
            "obligation_id": "guidance_only",
            "role": "critique_writer_guidance",
            "statement": "Separate direct outcome evidence from application guidance.",
        }
    )

    report = build_canonical_decision_writer_packet_quality_report(canonical)

    assert "source_id_missing_from_canonical_rows" not in report["warnings"]


def test_quality_synthesis_packet_preserves_source_appraisal_for_writer_notes() -> None:
    scaffold = _scaffold()
    scaffold["source_evidence_cards"]["cards"][0]["source_title"] = "Outcome Study"
    scaffold["source_evidence_cards"]["cards"][0]["evidence_type"] = "observational cohort study"
    scaffold["source_evidence_cards"]["cards"][0]["outcome_or_endpoint"] = "final outcome"
    scaffold["evidence_quality_report"] = {
        "schema_id": "evidence_quality_report_v1",
        "quality_components": {"sc0001": {"directness": "direct", "overall": "usable"}},
    }
    scaffold["source_appraisal_report"] = build_source_appraisal_report(
        source_evidence_cards=scaffold["source_evidence_cards"],
        evidence_quality_report=scaffold["evidence_quality_report"],
    )
    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    appraised_items = [
        item
        for item in packet["evidence_items"]
        if item.get("source_appraisal", {}).get("status") == "ready"
    ]
    canonical = packet["canonical_decision_writer_packet"]

    assert appraised_items
    assert canonical["quality_report"]["informative_source_weight_note_count"] >= 1
    assert "source_weight_notes_uninformative" not in canonical["quality_report"]["warnings"]
    assert any(
        "association_not_causation" in row.get("not_enough_for", [])
        for row in canonical["source_weight_notes"]
    )
    assert any(row.get("reader_facing_limit") for row in canonical["source_weight_judgments"])
    language_contract = next(row for row in canonical["evidence_language_contracts"] if row.get("source_ids") == ["s1"])
    assert language_contract["evidence_design"] == "observational"
    assert "is associated with" in language_contract["allowed_language"]
    assert "causes" in language_contract["avoid_language"]
    assert "observational evidence" in language_contract["must_qualify_with"]


def test_canonical_retention_routes_missing_items_to_targeted_repair() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = "## Decision Memo\n\n**Decision Question:** Should the city adopt option A for flood protection?\n\nOption A reduced flood losses by 25% [s1]."

    retention = build_memo_ready_packet_retention_report(memo, packet)
    repair_prompt = build_memo_ready_packet_repair_prompt(memo, packet, retention)

    assert retention["validation_basis"] == "canonical_decision_writer_packet"
    assert retention["canonical_packet_validation"] == "warning"
    assert any(issue.get("issue_type") == "missing_canonical_retention_item" for issue in retention["issues"])
    assert "missing_canonical_items" in repair_prompt
    assert "Repair missing canonical items" in repair_prompt
