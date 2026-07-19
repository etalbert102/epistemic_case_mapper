from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import (
    _project_prioritized_retention_packet,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_evaluation import (
    build_arm_comparison_to_current,
    resolve_current_baseline,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_b import (
    _bounded_mandatory_ids,
    _calibrated_bottom_line,
    _contract_for_arm_b,
    _prompt_decision_anchor,
    _short_decision_title,
    audit_prompt_submissions,
    build_arm_b_projection,
    load_frozen_arm_b_inputs,
    run_arm_b_b0,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_c import (
    build_arm_c_prioritization_prompt,
    build_arm_c_projection,
    normalize_arm_c_prioritized_argument_ids,
    reconcile_arm_c_owned_dispositions,
    run_arm_c_prioritization,
    verify_arm_c_prioritized_argument,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_evidence_anchoring import build_evidence_expression_contracts
from epistemic_case_mapper.model_backends import ModelBackendResult


FROZEN_EGGS = Path(__file__).resolve().parent / "fixtures" / "prioritized_evidence_argument_arm_b"


def test_arm_b_bottom_line_does_not_let_single_surrogate_carry_broad_answer() -> None:
    bottom_line = _calibrated_bottom_line(
        {
            "bounded_answer": (
                "Option A should be treated as neutral because a single dose did not change endothelial function. "
                "However, the answer is bounded by high-dose thresholds in narrower populations."
            ),
            "confidence": "medium",
            "scope_boundaries": ["Narrower populations require separate treatment."],
        }
    )

    assert "because a single dose" not in bottom_line
    assert "study-specific higher-exposure findings" in bottom_line
    assert "Confidence: medium" in bottom_line
    assert "bounded read of the current evidence" in bottom_line


def test_arm_b_bottom_line_removes_unsupported_scope_examples() -> None:
    bottom_line = _calibrated_bottom_line(
        {
            "bounded_answer": "Treat the exposure as neutral except in narrower groups (e.g., older adults with type 2 diabetes).",
            "confidence": "medium",
        }
    )

    assert "older adults" not in bottom_line
    assert "type 2 diabetes" not in bottom_line
    assert "narrower groups" in bottom_line


def test_arm_b_prompt_anchor_exposes_scope_rule_not_uncontracted_scope_details() -> None:
    anchor = _prompt_decision_anchor(
        {
            "decision_question": "What follows?",
            "bounded_answer": "Use the default except in narrower groups (e.g., older adults).",
            "confidence": "medium",
            "scope_boundaries": ["Older adults require separate treatment."],
            "do_not_overstate": ["Do not generalize."],
        }
    )

    assert "scope_boundaries" not in anchor
    assert "do_not_overstate" not in anchor
    assert "older adults" not in anchor["bounded_answer"]
    assert "However" not in anchor["bounded_answer"]
    assert "bounded read" in anchor["bounded_answer"]
    assert "only when a section evidence contract supports it" in anchor["scope_rule"]


def test_arm_b_projection_keeps_synthesis_constraints_section_local() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))
    answer = next(row for row in projection["section_packets"] if row["section_id"] == "answer_evidence")
    answer_contract_ids = {
        row["evidence_id"] for row in answer["evidence_expression_contracts"]
    }

    assert set(answer["synthesis_constraints"].get("surrogate_or_mechanistic_evidence_ids", [])).issubset(
        answer_contract_ids
    )
    assert all(set(move.get("evidence_item_ids", [])).issubset(answer_contract_ids) for move in answer["owned_moves"])
    assert all("point" not in move and "quantities" not in move for move in answer["owned_moves"])


def test_arm_b_prompt_exposes_source_evidence_and_synthesis_constraints() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))
    prompt = projection["section_plan"]["sections"][0]["prompt"]

    assert '"synthesis_constraints"' in prompt
    assert prompt.startswith("Section task: answer_evidence | Why This Is the Best Current Read\n")
    assert "source_evidence excerpts as the controlling factual surface" in prompt
    assert "must not be presented as sufficient by itself" in prompt


def test_arm_b_projection_resolves_eggs_writer_ownership() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))

    assert projection["status"] == "pass"
    required = projection["section_contract_overlap_report"]["required_by_section"]
    assert required["answer_evidence"] == [
        "decision_writer_item_001",
        "decision_writer_item_002",
        "decision_writer_item_003",
        "decision_writer_item_011",
    ]
    assert required["counterweights"] == [
        "decision_writer_item_004",
        "decision_writer_item_005",
        "decision_writer_item_007",
        "decision_writer_item_008",
    ]
    assert required["practical_implication"] == []
    assert projection["projection_evaluation_packet"]["lineage_fanout"]["claim:eggs_c024"] == [
        "decision_writer_item_001",
        "decision_writer_item_002",
    ]
    assert projection["projection_evaluation_packet"]["ownership"]["decision_writer_item_004"] == "counterweights"
    assert projection["projection_evaluation_packet"]["ownership"]["decision_writer_item_005"] == "counterweights"


def test_arm_b_projection_suppresses_source_weighting_and_legacy_packet_roots() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))
    section_ids = [row["section_id"] for row in projection["section_packets"]]
    serialized = str(projection["section_packets"])

    assert section_ids == ["answer_evidence", "counterweights", "practical_implication"]
    assert "source_weighting" not in section_ids
    assert "balanced_answer_frame" not in serialized
    assert "bluf_contract" not in serialized
    assert "analyst_decision_spine" not in serialized
    assert "reader_judgment_packet" not in serialized


def test_arm_b_projection_marks_section_owned_contract_scope() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))

    section_plan = projection["section_plan"]

    assert section_plan["evidence_contract_scope"] == "section_owned"
    assert all(section["prompt_mode"] == "arm_b_slim" for section in section_plan["sections"])


def test_arm_b_projection_treats_warning_references_as_annotations() -> None:
    inputs = deepcopy(load_frozen_arm_b_inputs(FROZEN_EGGS))
    moves = inputs["memo_ready_packet"]["canonical_decision_writer_packet"]["decision_argument_contract"]["argument_moves"]
    moves[0].setdefault("evidence_item_ids", []).append("warning:memo_warning_999")

    projection = build_arm_b_projection(inputs)

    assert projection["status"] == "pass"
    assert "unknown_evidence_id:warning:memo_warning_999" not in projection["projection_evaluation_packet"]["issues"]


def test_arm_b_mandatory_cap_prefers_explicit_canonical_items() -> None:
    mandatory = {f"e{i}" for i in range(1, 10)}
    ownership = {evidence_id: "answer_evidence" for evidence_id in mandatory}
    canonical = {
        "decision_argument_contract": {
            "argument_moves": [{"evidence_item_ids": ["e9", "e8"]}],
        }
    }

    selected = _bounded_mandatory_ids(mandatory, ownership=ownership, canonical=canonical)

    assert len(selected) == 6
    assert {"e8", "e9"}.issubset(selected)


def test_arm_b_mandatory_cap_prefers_source_specific_contracts() -> None:
    mandatory = {f"e{i}" for i in range(1, 8)}
    ownership = {evidence_id: "answer_evidence" for evidence_id in mandatory}
    canonical = {
        "decision_argument_contract": {
            "argument_moves": [{"evidence_item_ids": [f"e{i}" for i in range(1, 8)]}],
        }
    }
    contracts = {
        **{f"e{i}": {"source_ids": [f"s{i}"]} for i in range(2, 6)},
        **{f"e{i}": {"source_ids": ["s1", "s2"]} for i in (1, 6, 7)},
    }

    selected = _bounded_mandatory_ids(
        mandatory,
        ownership=ownership,
        canonical=canonical,
        contracts_by_id=contracts,
    )

    assert {"e2", "e3", "e4", "e5"}.issubset(selected)
    assert "e7" not in selected


def test_arm_b_mandatory_cap_compresses_oversized_packets() -> None:
    mandatory = {f"a{i}" for i in range(1, 9)} | {f"c{i}" for i in range(1, 7)}
    ownership = {
        **{f"a{i}": "answer_evidence" for i in range(1, 9)},
        **{f"c{i}": "counterweights" for i in range(1, 7)},
    }

    selected = _bounded_mandatory_ids(mandatory, ownership=ownership, canonical={})

    assert len([item for item in selected if item.startswith("a")]) == 3
    assert len([item for item in selected if item.startswith("c")]) == 4


def test_arm_b_contract_uses_controlling_source_excerpt_as_claim() -> None:
    contract = _contract_for_arm_b(
        {
            "evidence_id": "e1",
            "claim": "Aggregate claim adds an unsupported population and endpoint.",
            "source_evidence": [
                {"source_id": "s1", "excerpts": ["The trial found no significant change in the measured outcome."]}
            ],
            "required_quantity_atoms": [
                {
                    "value": "1.19",
                    "interpretation": "Legacy interpretation adds the wrong endpoint.",
                    "assertion_bundle": {"allowed_inference": "Associated with all-cause mortality.", "source_ids": ["s1"]},
                }
            ],
        },
        required=True,
    )

    assert contract["claim"] == "The trial found no significant change in the measured outcome."
    assert contract["required_quantity_atoms"][0]["interpretation"] == "Associated with all-cause mortality."
    assert contract["required"] is True


def test_arm_b_title_truncation_does_not_split_word() -> None:
    title = _short_decision_title(
        "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial?"
    )

    assert len(title) <= 80
    assert title.endswith("harmful")


def test_arm_b_practical_section_has_no_uncontracted_evidence_channel() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))
    practical = next(row for row in projection["section_packets"] if row["section_id"] == "practical_implication")
    prompt = next(row["prompt"] for row in projection["section_plan"]["sections"] if row["section_id"] == "practical_implication")

    assert practical["citation_mode"] == "none"
    assert "reference_moves" not in practical
    assert "Do not add evidence tags, source citations, study details, or quantities" in prompt


def test_load_frozen_inputs_uses_analyst_packet_when_canonical_packet_is_not_usable(tmp_path) -> None:
    briefing_dir = tmp_path / "briefing"
    briefing_dir.mkdir()
    (briefing_dir / "memo_ready_packet.json").write_text(
        json.dumps({"decision_usefulness_packet": {}, "evidence_items": []}),
        encoding="utf-8",
    )
    (briefing_dir / "analyst_memo_ready_packet.json").write_text(
        json.dumps(
            {
                "decision_question": "Should the team proceed?",
                "evidence_items": [{"item_id": "E1", "source_id": "S1", "text": "Relevant finding."}],
                "canonical_decision_writer_packet": {"answer_sections": []},
            }
        ),
        encoding="utf-8",
    )

    inputs = load_frozen_arm_b_inputs(briefing_dir)

    assert inputs["memo_ready_packet_source"] == "analyst_memo_ready_packet.json"
    assert inputs["memo_ready_packet"]["decision_question"] == "Should the team proceed?"


def test_comparison_to_current_marks_missing_baseline_not_applicable(tmp_path) -> None:
    briefing_dir = tmp_path / "briefing"
    briefing_dir.mkdir()
    baseline = resolve_current_baseline(briefing_dir)

    comparison = build_arm_comparison_to_current(
        baseline_memo_path=Path("__missing_baseline_memo__.md"),
        baseline_report_path=Path("__missing_baseline_report__.json"),
        candidate_memo="## Answer\nA supported answer. {E:E1}",
        candidate_report={"status": "accepted", "accepted": True},
        prompt_audit={"status": "pass", "prompt_count": 1, "retry_prompt_count": 0},
        elapsed_seconds=1.0,
        baseline_resolution=baseline,
    )

    assert baseline["status"] == "missing"
    assert comparison["status"] == "not_applicable"
    assert comparison["quality_assessment"]["semantic_flags"] == ["baseline_unavailable"]


def test_arm_c_normalizes_upstream_lineage_ids_to_writer_evidence_ids() -> None:
    inputs = {
        "memo_ready_packet": {
            "decision_question": "What follows?",
            "evidence_items": [
                {
                    "item_id": "writer_item_001",
                    "lineage": {"covered_evidence_item_ids": ["claim:c001", "relation:r001"]},
                }
            ],
        },
        "analyst_decision_model": {
            "decision_question": "What follows?",
            "direct_answer": "The answer is bounded.",
            "confidence": "medium",
        },
        "evidence_budget": {"foreground_evidence_item_ids": ["relation:r001"], "counterweight_evidence_item_ids": []},
    }
    payload = {
        "schema_id": "arm_c_prioritized_argument_v1",
        "decision_question": "What follows?",
        "frozen_direct_answer": "The answer is bounded.",
        "confidence": "medium",
        "argument_thesis": "The answer follows from the bounded relation.",
        "moves": [
            {
                "move_id": "m1",
                "primary_section": "answer_evidence",
                "proposition": "A relation carries the answer.",
                "warrant": "The relation is in the verified lineage.",
                "decision_effect": "It supports the answer.",
                "evidence_item_ids": ["relation:r001"],
            }
        ],
        "evidence_accounting": [
            {"evidence_item_id": "relation:r001", "disposition": "owned", "rationale": "Used in the move."}
        ],
    }

    normalized, normalization_report = normalize_arm_c_prioritized_argument_ids(inputs, payload)
    report = verify_arm_c_prioritized_argument(inputs, normalized)

    assert normalization_report["rewrite_count"] == 2
    assert normalized["moves"][0]["evidence_item_ids"] == ["writer_item_001"]
    assert normalized["evidence_accounting"][0]["evidence_item_id"] == "writer_item_001"
    assert report["status"] == "pass"


def test_arm_c_projection_uses_prioritized_move_required_ids_not_legacy_must_use() -> None:
    base_inputs = load_frozen_arm_b_inputs(FROZEN_EGGS)
    packet = dict(base_inputs["memo_ready_packet"])
    items = []
    for item in packet["evidence_items"]:
        copied = dict(item)
        copied["must_use"] = copied["item_id"] in {"decision_writer_item_001", "decision_writer_item_004"}
        copied["obligation_level"] = "must_include" if copied["must_use"] else copied.get("obligation_level", "")
        items.append(copied)
    packet["evidence_items"] = items
    inputs = {**base_inputs, "memo_ready_packet": packet}
    argument = {
        "schema_id": "arm_c_prioritized_argument_v1",
        "moves": [
            {
                "move_id": "m1",
                "primary_section": "answer_evidence",
                "proposition": "Use the selected support.",
                "warrant": "It carries the answer.",
                "decision_effect": "It supports the answer.",
                "evidence_item_ids": ["decision_writer_item_001"],
            }
        ],
    }

    projection = build_arm_c_projection(inputs, argument)

    assert projection["status"] == "pass"
    required = projection["section_contract_overlap_report"]["required_by_section"]
    assert required["answer_evidence"] == ["decision_writer_item_001"]
    assert "decision_writer_item_004" not in projection["projection_evaluation_packet"]["mandatory_evidence_ids"]


def test_arm_c_verification_rejects_owned_evidence_without_required_move() -> None:
    inputs = load_frozen_arm_b_inputs(FROZEN_EGGS)
    analyst = inputs["analyst_decision_model"]
    argument = {
        "schema_id": "arm_c_prioritized_argument_v1",
        "decision_question": analyst["decision_question"],
        "frozen_direct_answer": analyst["direct_answer"],
        "confidence": analyst["confidence"],
        "argument_thesis": "Use the owned evidence assigned to required moves.",
        "moves": [
            {
                "move_id": "m1",
                "primary_section": "answer_evidence",
                "proposition": "The selected evidence supports the answer.",
                "warrant": "It is the prioritized support item.",
                "decision_effect": "It supports the current read.",
                "required": True,
                "evidence_item_ids": ["decision_writer_item_001"],
            }
        ],
        "evidence_accounting": [
            {"evidence_item_id": "decision_writer_item_001", "disposition": "owned", "rationale": "Used."},
            {"evidence_item_id": "decision_writer_item_004", "disposition": "owned", "rationale": "Not used."},
        ],
    }

    report = verify_arm_c_prioritized_argument(inputs, argument)

    assert report["status"] == "fail"
    assert report["owned_evidence_not_in_required_move_ids"] == ["decision_writer_item_004"]
    assert "owned_evidence_not_in_required_move:decision_writer_item_004" in report["issues"]


def test_prioritized_retention_packet_limits_mandatory_scope_without_dropping_context() -> None:
    packet = {
        "evidence_items": [
            {"item_id": "e1", "must_use": True, "obligation_level": "must_include"},
            {"item_id": "e2", "must_use": True, "obligation_level": "must_include"},
        ],
        "memo_obligations": {
            "obligations": [
                {"obligation_id": "o1", "evidence_item_ids": ["e1", "e2"]},
                {"obligation_id": "o2", "evidence_item_ids": ["e2"]},
                {"obligation_id": "o3", "statement": "Retain this packet-level warning."},
            ]
        },
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {"check_id": "c1", "evidence_item_ids": ["e1"]},
                {"check_id": "c2", "evidence_item_ids": ["e2"]},
            ]
        },
    }
    argument = {
        "evidence_accounting": [
            {"evidence_item_id": "e1", "disposition": "owned"},
            {"evidence_item_id": "e2", "disposition": "demoted"},
        ]
    }
    projection = {"projection_evaluation_packet": {"mandatory_evidence_ids": ["e1"]}}

    projected = _project_prioritized_retention_packet(
        packet,
        prioritized_argument=argument,
        projection=projection,
    )

    assert len(projected["evidence_items"]) == 2
    assert projected["evidence_items"][0]["must_use"] is True
    assert projected["evidence_items"][1]["must_use"] is False
    assert projected["evidence_items"][1]["obligation_level"] == "supporting"
    assert projected["memo_obligations"]["obligations"] == [
        {"obligation_id": "o1", "evidence_item_ids": ["e1"]},
        {"obligation_id": "o3", "statement": "Retain this packet-level warning."},
    ]
    assert projected["canonical_decision_writer_packet"]["mandatory_retention_checklist"] == [
        {"check_id": "c1", "evidence_item_ids": ["e1"]}
    ]
    assert projected["prioritized_retention_scope"]["required_evidence_item_ids"] == ["e1"]
    assert packet["evidence_items"][1]["must_use"] is True


def test_arm_c_prioritization_repairs_owned_evidence_without_required_move(monkeypatch) -> None:
    inputs = load_frozen_arm_b_inputs(FROZEN_EGGS)
    analyst = inputs["analyst_decision_model"]
    base = {
        "schema_id": "arm_c_prioritized_argument_v1",
        "decision_question": analyst["decision_question"],
        "frozen_direct_answer": analyst["direct_answer"],
        "confidence": analyst["confidence"],
        "argument_thesis": "Use a bounded prioritized argument.",
        "moves": [
            {
                "move_id": "m1",
                "primary_section": "answer_evidence",
                "proposition": "The selected evidence supports the answer.",
                "warrant": "It is the primary support.",
                "decision_effect": "It supports the current read.",
                "evidence_item_ids": ["decision_writer_item_001"],
                "required": True,
            }
        ],
        "evidence_accounting": [
            {"evidence_item_id": "decision_writer_item_001", "disposition": "owned", "rationale": "Used."},
            {"evidence_item_id": "decision_writer_item_004", "disposition": "owned", "rationale": "Initially unused."},
        ],
    }
    repaired = json.loads(json.dumps(base))
    repaired["evidence_accounting"][1]["disposition"] = "demoted"
    responses = iter([base, repaired])

    def fake_backend(prompt: str, backend: str, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(next(responses)), backend=backend)

    monkeypatch.setattr(
        "epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_c.run_model_backend",
        fake_backend,
    )

    result = run_arm_c_prioritization(
        inputs,
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["accepted"] is True
    assert result["report"]["semantic_repair_attempted"] is True
    assert result["report"]["initial_verification_report"]["status"] == "fail"
    assert result["prioritized_argument"]["evidence_accounting"][1]["disposition"] == "demoted"


def test_arm_c_owned_disposition_reconciliation_demotes_residual_unassigned_items() -> None:
    payload = {
        "moves": [
            {"move_id": "m1", "required": True, "evidence_item_ids": ["e1"]},
            {"move_id": "m2", "required": False, "evidence_item_ids": ["e2"]},
        ],
        "evidence_accounting": [
            {"evidence_item_id": "e1", "disposition": "owned"},
            {"evidence_item_id": "e2", "disposition": "owned"},
            {"evidence_item_id": "e3", "disposition": "background"},
        ],
    }

    reconciled, report = reconcile_arm_c_owned_dispositions(payload)

    assert reconciled["evidence_accounting"][0]["disposition"] == "owned"
    assert reconciled["evidence_accounting"][1]["disposition"] == "demoted"
    assert reconciled["evidence_accounting"][2]["disposition"] == "background"
    assert report["rewritten_evidence_item_ids"] == ["e2"]
    assert payload["evidence_accounting"][1]["disposition"] == "owned"


def test_arm_c_prompt_validation_and_projection_are_bundle_native() -> None:
    bundle = {
        "schema_id": "source_assertion_bundle_v1",
        "evidence_bundle_id": "bundle_demo_001",
        "value": "RR 1.17 (95% CI 1.08 to 1.27)",
        "estimate": "1.17",
        "interval": "95% CI 1.08 to 1.27",
        "statistic_type": "relative_risk",
        "endpoint": "cardiovascular disease",
        "allowed_inference": "Associated with higher cardiovascular disease risk.",
        "forbidden_inference": "Do not present observational association as causal.",
        "source_ids": ["src001"],
    }
    inputs = load_frozen_arm_b_inputs(FROZEN_EGGS)
    packet = dict(inputs["memo_ready_packet"])
    items = []
    for item in packet["evidence_items"]:
        copied = dict(item)
        if copied.get("item_id") == "decision_writer_item_001":
            copied["assertion_bundles"] = [bundle]
            copied["quantities"] = [
                {
                    "value": bundle["value"],
                    "evidence_bundle_id": bundle["evidence_bundle_id"],
                    "assertion_bundle": bundle,
                    "endpoint": bundle["endpoint"],
                }
            ]
        items.append(copied)
    packet["evidence_items"] = items
    inputs = {**inputs, "memo_ready_packet": packet}

    prompt = build_arm_c_prioritization_prompt(inputs)
    assert "evidence_bundle_registry" in prompt
    assert "bundle_demo_001" in prompt

    argument = {
        "schema_id": "arm_c_prioritized_argument_v1",
        "decision_question": inputs["analyst_decision_model"]["decision_question"],
        "frozen_direct_answer": inputs["analyst_decision_model"]["direct_answer"],
        "confidence": inputs["analyst_decision_model"]["confidence"],
        "argument_thesis": "The answer should reflect the selected source-bound quantity.",
        "moves": [
            {
                "move_id": "m1",
                "primary_section": "answer_evidence",
                "proposition": "Use the selected quantitative association.",
                "warrant": "The bundle preserves the statistic type, interval, and allowed inference.",
                "decision_effect": "It supports a calibrated answer.",
                "evidence_item_ids": ["decision_writer_item_001"],
                "evidence_bundle_ids": ["bundle_demo_001"],
                "bundle_intended_uses": [
                    {
                        "evidence_bundle_id": "bundle_demo_001",
                        "intended_use": "Report the RR with its confidence interval as an association.",
                    }
                ],
                "required": True,
            }
        ],
        "evidence_accounting": [
            {"evidence_item_id": "decision_writer_item_001", "disposition": "owned", "rationale": "Selected bundle carrier."}
        ],
    }

    report = verify_arm_c_prioritized_argument(inputs, argument)
    projection = build_arm_c_projection(inputs, argument)

    assert report["status"] == "pass"
    assert report["known_evidence_bundle_id_count"] == 1
    assert projection["status"] == "pass"
    assert projection["projection_evaluation_packet"]["selected_evidence_bundle_ids"] == ["bundle_demo_001"]
    assert "bundle_demo_001" in json.dumps(projection["section_packets"])


def test_expression_contracts_preserve_source_assertion_bundles() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "E1",
                "role": "strongest_support",
                "reader_claim": "Higher exposure was associated with higher risk.",
                "source_ids": ["S1"],
                "assertion_bundles": [
                    {
                        "evidence_bundle_id": "bundle_demo_001",
                        "value": "RR 1.17 (95% CI 1.08 to 1.27)",
                        "endpoint": "cardiovascular disease",
                    }
                ],
                "quantities": [
                    {
                        "value": "RR 1.17 (95% CI 1.08 to 1.27)",
                        "evidence_bundle_id": "bundle_demo_001",
                        "assertion_bundle": {
                            "evidence_bundle_id": "bundle_demo_001",
                            "value": "RR 1.17 (95% CI 1.08 to 1.27)",
                            "endpoint": "cardiovascular disease",
                        },
                    }
                ],
            }
        ]
    }

    contracts = build_evidence_expression_contracts(packet)

    assert contracts[0]["evidence_bundle_ids"] == ["bundle_demo_001"]
    assert contracts[0]["assertion_bundles"][0]["endpoint"] == "cardiovascular disease"


def test_production_synthesis_uses_prioritized_argument_path(monkeypatch, tmp_path: Path) -> None:
    inputs = load_frozen_arm_b_inputs(FROZEN_EGGS)
    packet = inputs["memo_ready_packet"]
    analyst = inputs["analyst_decision_model"]
    calls: list[dict[str, object]] = []

    def fake_backend(prompt: str, backend: str, **kwargs) -> ModelBackendResult:
        calls.append({"prompt": prompt, "json_mode": kwargs.get("json_mode"), "response_schema": kwargs.get("response_schema")})
        if kwargs.get("response_schema"):
            payload = {
                "schema_id": "arm_c_prioritized_argument_v1",
                "decision_question": analyst["decision_question"],
                "frozen_direct_answer": analyst["direct_answer"],
                "confidence": analyst["confidence"],
                "argument_thesis": "Use the prioritized evidence to explain the decision answer.",
                "moves": [
                    {
                        "move_id": "m1",
                        "primary_section": "answer_evidence",
                        "move_type": "primary_support",
                        "proposition": "The strongest evidence carries the current read.",
                        "warrant": "This item directly addresses the decision question.",
                        "decision_effect": "It supports the answer.",
                        "evidence_item_ids": ["decision_writer_item_001"],
                        "required": True,
                    },
                    {
                        "move_id": "m2",
                        "primary_section": "counterweights",
                        "move_type": "counterweight",
                        "proposition": "Counterevidence bounds the current read.",
                        "warrant": "The decision turns on whether this limitation applies.",
                        "decision_effect": "It calibrates confidence.",
                        "evidence_item_ids": ["decision_writer_item_004"],
                        "required": True,
                    },
                ],
                "evidence_accounting": [
                    {"evidence_item_id": "decision_writer_item_001", "disposition": "owned", "rationale": "Primary support."},
                    {"evidence_item_id": "decision_writer_item_004", "disposition": "owned", "rationale": "Primary counterweight."},
                ],
            }
            return ModelBackendResult(text=json.dumps(payload), backend=backend)
        heading = _heading_from_prompt(prompt)
        evidence_ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        tags = " ".join(f"{{E:{evidence_id}}}" for evidence_id in evidence_ids)
        body = (
            "This section uses the prioritized argument rather than the generic packet plan. "
            f"The source-grounded evidence is retained here {tags}."
        )
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_c.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(
        packet,
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
        production_context=inputs,
        artifacts=tmp_path,
    )

    assert result["report"].get("prioritized_argument_synthesis") is True, result["report"]
    assert result["report"]["prioritized_argument_synthesis_report"]["accepted"] is True
    assert (tmp_path / "prioritized_evidence_argument.json").exists()
    assert (tmp_path / "prioritized_argument_section_synthesis_packets.json").exists()
    assert any(call["response_schema"] for call in calls)
    assert "Prioritized evidence argument section synthesis" in result["prompt"]
    assert "## Why This Is the Best Current Read" in result["memo"]


def test_arm_b_b0_captures_initial_and_retry_prompts(tmp_path) -> None:
    result = run_arm_b_b0(briefing_dir=FROZEN_EGGS, output_dir=tmp_path, force_retry=True)

    assert result["report"]["status"] == "pass"
    assert result["generation"]["report"]["status"] == "accepted"
    assert result["prompt_submission_audit"]["status"] == "pass"
    assert result["prompt_submission_audit"]["retry_prompt_count"] >= 1
    assert (tmp_path / "prompt_submission_audit.json").exists()
    assert (tmp_path / "projection_evaluation_packet.json").exists()
    assert (tmp_path / "frozen_inputs" / "input_hashes.json").exists()
    assert result["warning_adjudication_report"]["unadjudicated_count"] == 0


def test_arm_b_prompt_audit_flags_legacy_context() -> None:
    audit = audit_prompt_submissions(
        [
            {
                "section_id": "answer_evidence",
                "attempt": 1,
                "prompt": '### Slim argument packet\n{"balanced_answer_frame": {}}\n',
            }
        ]
    )

    assert audit["status"] == "fail"
    assert any("balanced_answer_frame" in issue for issue in audit["issues"])


def _heading_from_prompt(prompt: str) -> str:
    match = re.search(r"exactly(?: with)?: ## (.+)", prompt)
    if not match:
        match = re.search(r"Output starts exactly with: ## (.+)", prompt)
    if not match:
        match = re.search(r"Output must start exactly with: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
