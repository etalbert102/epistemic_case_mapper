from __future__ import annotations

import json

from epistemic_case_mapper.io import write_json
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_decision_usefulness_memo_repair_prompt,
    build_memo_ready_packet_repair_prompt,
)
from epistemic_case_mapper.map_briefing_model_context import build_model_call_context_inventory, build_model_context_audit


def test_model_context_audit_separates_record_only_and_model_context(tmp_path) -> None:
    packet_path = tmp_path / "section_synthesis_packets.json"
    write_json(
        packet_path,
        {
            "packets": [
                {
                    "title": "Why This Read",
                    "packet": {"debug_only": "x" * 1000},
                    "model_packet": {
                        "schema_id": "model_section_packet_v1",
                        "section_thesis": "Explain the decision logic.",
                        "prohibited_repetition": [{"slot": "Boundary", "owner_section": "Scope"}],
                    },
                }
            ]
        },
    )

    audit = build_model_context_audit(
        backend="prompt",
        legacy_prompt="legacy prompt",
        section_packets_path=packet_path,
        reader_rewrite_prompt="",
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    section = stages["section_rewrite"]["sections"][0]

    assert stages["whole_briefing_legacy_prompt"]["status"] == "record_only_legacy_prompt"
    assert "global_memo_plan" not in stages
    assert section["model_to_debug_char_ratio"] < 1
    assert "negative_anchor_terms_visible" not in section["pollution_flags"]


def test_model_context_audit_flags_visible_negative_anchor_terms(tmp_path) -> None:
    packet_path = tmp_path / "section_synthesis_packets.json"
    write_json(
        packet_path,
        {
            "packets": [
                {
                    "title": "Practical Read",
                    "packet": {},
                    "model_packet": {"prohibited_repetition": [{"anchor_terms_to_avoid_repeating": ["42"]}]},
                }
            ]
        },
    )

    audit = build_model_context_audit(
        backend="fake",
        legacy_prompt="",
        section_packets_path=packet_path,
        reader_rewrite_prompt=json.dumps({"edits": []}),
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    section = stages["section_rewrite"]["sections"][0]
    assert "negative_anchor_terms_visible" in section["pollution_flags"]
    assert stages["reader_memo_edit_suggestions"]["sent_to_model"] is True


def test_model_context_audit_flags_broad_reader_rewrite_contract() -> None:
    prompt = """
    You are a controlled prose editor.

    Evidence contract:
    {
      "answer_frame": {"direct_answer": "Use only conditionally."},
      "option_comparison": {"options": []},
      "required_evidence": [{"claim": "A claim.", "source": "Doc"}],
      "required_gaps": ["Missing comparator."]
    }

    Deterministic memo to inspect:
    ## Decision Brief
    """

    audit = build_model_context_audit(
        backend="fake",
        legacy_prompt="",
        section_packets_path=None,
        reader_rewrite_prompt=prompt,
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    reader_stage = stages["reader_memo_edit_suggestions"]
    assert reader_stage["sent_to_model"] is True
    assert "broad_evidence_contract_visible" in reader_stage["pollution_flags"]
    assert "answer_frame_visible" in reader_stage["pollution_flags"]
    assert "option_comparison_visible" in reader_stage["pollution_flags"]
    assert "required_evidence_visible" in reader_stage["pollution_flags"]


def test_model_context_audit_accepts_compact_reader_rewrite_prompt() -> None:
    prompt = """
    You are a final memo prose editor.

    Decision question: Should this be used?
    Protected spans:
    - ## Decision Brief
    - **Confidence:** medium
    Polish diagnosis:
    - smooth transition in Practical Read

    Memo:
    ## Decision Brief
    """

    audit = build_model_context_audit(
        backend="fake",
        legacy_prompt="",
        section_packets_path=None,
        reader_rewrite_prompt=prompt,
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    reader_stage = stages["reader_memo_edit_suggestions"]
    assert reader_stage["sent_to_model"] is True
    assert reader_stage["pollution_flags"] == []


def test_model_context_audit_flags_active_prompt_pollution() -> None:
    audit = build_model_context_audit(
        backend="ollama:test",
        legacy_prompt="",
        section_packets_path=None,
        reader_rewrite_prompt="",
        active_prompts={
            "analyst_quantity_binding": '{"deterministic_memo_use": "yes", "source_excerpt": "long"}',
            "memo_ready_synthesis": '{"excluded_evidence_log": [], "lineage_report": {}}',
            "packet_refinement": '{"packet_sufficiency_report": {"status": "skipped_prompt_backend"}}',
        },
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    active = {row["stage"]: row for row in stages["active_model_prompts"]["prompts"]}

    assert stages["active_model_prompts"]["sent_to_model"] is True
    assert "deterministic_judgment_label_visible" in active["analyst_quantity_binding"]["pollution_flags"]
    assert "writer_debug_record_visible" in active["memo_ready_synthesis"]["pollution_flags"]
    assert "validator_report_visible" in active["packet_refinement"]["pollution_flags"]
    assert "skipped_backend_report_visible" in active["packet_refinement"]["pollution_flags"]


def test_model_context_audit_inventories_upstream_prompt_artifacts(tmp_path) -> None:
    claim_dir = tmp_path / "claim_sources"
    relation_dir = tmp_path / "relation_batches"
    claim_dir.mkdir()
    relation_dir.mkdir()
    (claim_dir / "source_a_prompt.txt").write_text(
        "Task: extract claims\nDecision question: Should option A be used?\nSource ID: s1\n",
        encoding="utf-8",
    )
    (relation_dir / "batch_001_prompt.txt").write_text(
        "Task: classify relation\nDecision question: Should option A be used?\nClaim A: c1\nClaim B: c2\n",
        encoding="utf-8",
    )

    audit = build_model_context_audit(
        backend="ollama:test",
        legacy_prompt="",
        section_packets_path=None,
        reader_rewrite_prompt="",
        prompt_artifact_root=tmp_path,
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    inventory = stages["upstream_model_call_inventory"]
    records = {row["stage"]: row for row in inventory["prompts"]}

    assert inventory["prompt_count"] == 2
    assert records["source_claim_extraction"]["context_scope"] == "source_local"
    assert records["source_claim_extraction"]["decision_question_present"] is True
    assert records["relation_batch_classification"]["context_scope"] == "small_batch_local"


def test_model_call_context_inventory_flags_polarity_without_answer_frame(tmp_path) -> None:
    relation_dir = tmp_path / "relation_batches"
    relation_dir.mkdir()
    (relation_dir / "batch_001_prompt.txt").write_text(
        '{"task": "classify", "allowed": ["load_bearing_primary_support", "load_bearing_counterweight"]}',
        encoding="utf-8",
    )

    inventory = build_model_call_context_inventory(tmp_path)

    assert "answer_frame_context_missing_for_polarity_labels" in inventory[0]["pollution_flags"]


def test_repair_prompts_keep_context_targeted_and_exclude_broad_reports() -> None:
    memo = "## Decision Brief\n\nCurrent answer [s1].\n"
    packet = {
        "decision_question": "Should option A be used?",
        "evidence_items": [
            {
                "item_id": "item_001",
                "role": "strongest_support",
                "reader_claim": "Option A is supported by the main source.",
                "source_label": "s1",
                "source_ids": ["s1"],
                "quantities": ["42%"],
                "decision_relevance": "Directly answers the question.",
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Source One"}],
        "canonical_decision_writer_packet": {"decision_question": "Should option A be used?"},
    }
    retention_report = {
        "issues": [{"issue_type": "missing_memo_ready_item", "item_id": "item_001", "missing_quantities": ["42%"]}],
        "missing_mandatory_count": 1,
        "unresolved_warning_count": 0,
        "canonical_packet_retention_report": {"issues": []},
        "warning_resolution_report": {},
    }
    usefulness_retention = {
        "issues": [
            {
                "obligation_type": "presentation_gap",
                "required_text": "State the practical implication.",
                "source_ids": ["s1"],
                "evidence_item_ids": ["item_001"],
                "presentation_type": "practical_implication",
                "repair_instruction": "Add one practical sentence.",
            }
        ]
    }

    prompts = [
        build_memo_ready_packet_repair_prompt(memo, packet, retention_report),
        build_decision_usefulness_memo_repair_prompt(memo, packet, usefulness_retention),
    ]

    for prompt in prompts:
        assert "packet_sufficiency_report" not in prompt
        assert "packet_critique_adjudication_report" not in prompt
        assert "lineage_report" not in prompt
        assert "raw output" not in prompt.lower()
        assert "full source" not in prompt.lower()
