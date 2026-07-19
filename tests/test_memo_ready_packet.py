from __future__ import annotations

import json
from pathlib import Path

import pytest

from epistemic_case_mapper.pipeline.briefing.map_briefing_final_outputs import ModelBackendConfig, write_final_reader_outputs
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import (
    build_memo_ready_final_polish_prompt,
    build_memo_ready_packet_repair_prompt,
    build_memo_ready_packet_retention_report,
    normalize_memo_ready_polish_text,
    run_memo_ready_json_final_polish_experiment,
    run_memo_ready_presentation_normalization,
    run_memo_ready_packet_repair,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_warning_packet import build_warning_resolution_report
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet import (
    build_quality_synthesis_packet_bundle,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_obligations import build_memo_obligation_packet
from epistemic_case_mapper.pipeline.briefing.map_briefing_simplification_comparison import build_pipeline_simplification_comparison
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold


def test_quality_synthesis_packet_builds_assembly_artifacts() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")

    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])

    assert result["packet_assembly_clusters"]["schema_id"] == "packet_assembly_clusters_v1"
    assert result["packet_role_assignment_report"]["schema_id"] == "packet_role_assignment_report_v1"
    assert result["diagnosticity_matrix"]["schema_id"] == "diagnosticity_matrix_v1"
    assert result["quantity_binding_report"]["schema_id"] == "quantity_binding_report_v1"
    assert result["packet_assembly_audit"]["schema_id"] == "packet_assembly_audit_v1"
    assert result["memo_ready_packet"]["schema_id"] == "memo_ready_packet_v1"
    assert result["memo_ready_packet_quality_report"]["schema_id"] == "memo_ready_packet_quality_report_v1"


def test_memo_ready_packet_preserves_roles_quantities_and_lineage() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    packet = result["memo_ready_packet"]

    roles = {item["role"] for item in packet["evidence_items"]}
    assert {"quantitative_anchor", "strongest_counterweight", "scope_boundary"} <= roles
    quantity_items = [item for item in packet["evidence_items"] if item["role"] == "quantitative_anchor"]
    assert any(quantity.get("value") == "25%" for item in quantity_items for quantity in item.get("quantities", []))
    assert all(item["lineage"]["derived_from_claim_ids"] for item in packet["evidence_items"] if item["must_use"])
    assert all(item.get("source_label") for item in packet["evidence_items"] if item["must_use"])
    assert all(item["argument"]["warrant"] for item in packet["evidence_items"] if item["must_use"])


def test_packet_assembly_keeps_cross_source_near_duplicates_separate() -> None:
    scaffold = _scaffold()
    scaffold["source_display_names"]["s4"] = "Second Outcome Study"
    scaffold["candidate_evidence_cards"]["cards"].append(
        {
            "candidate_card_id": "ec0004",
            "source_card_ids": ["sc0004"],
            "claim_ids": ["c4"],
            "source_ids": ["s4"],
            "source_titles": ["Second Outcome Study"],
            "claim": "Option A reduced flood losses by 25 percent in comparable river cities.",
            "role": "support",
            "evidence_roles": ["support"],
            "decision_relevance_score": 9,
            "inclusion_recommendation": "main_text",
            "inclusion_reason": "Independent confirmation.",
            "anchor_confidence": "exact",
            "quantity_values": ["25 percent"],
        }
    )
    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])

    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    kept_separate = result["packet_assembly_clusters"]["kept_separate_near_duplicates"]

    assert kept_separate
    assert any(row["reason"] == "kept_separate_due_to_distinct_blocking_key" for row in kept_separate)


def test_memo_ready_packet_demotes_challenge_language_from_support() -> None:
    scaffold = _scaffold()
    scaffold["argument_model"]["strongest_support"][0]["statement"] = "A technical critique challenges whether the main stopping argument applies."
    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])

    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    challenge_items = [item for item in packet["evidence_items"] if "challenges" in item["reader_claim"]]

    assert challenge_items
    assert all(item["role"] == "strongest_counterweight" for item in challenge_items)


def test_quantity_binding_excludes_unbound_quantities_from_mandatory_obligations() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    packet["evidence_bundles"].append(
        {
            "bundle_id": "bundle_unbound",
            "decision_role": "quantitative_anchor",
            "claim": "A floating quantity lacks source lineage.",
            "quantity_values": ["42%"],
            "weight": "high",
        }
    )

    result = build_quality_synthesis_packet_bundle(packet)
    binding = result["quantity_binding_report"]
    memo_ready = result["memo_ready_packet"]

    assert binding["unbound_quantity_group_count"] >= 1
    assert not any(
        item["reader_claim"] == "A floating quantity lacks source lineage." and item["must_use"]
        for item in memo_ready["evidence_items"]
    )


def test_memo_ready_packet_flags_malformed_generic_default_read_without_replacement() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    built["decision_briefing_packet"]["answer_frame"]["default_answer"] = (
        "{'classification': 'neutral_or_low_concern_under_stated_conditions', "
        "'current_read': 'State the default as neutral or low-concern under the stated conditions.'..."
    )

    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    packet = result["memo_ready_packet"]
    report = result["memo_ready_packet_quality_report"]

    assert "{'classification'" in packet["answer_spine"]["default_read"]
    assert any(issue["issue_type"] == "invalid_or_scaffolded_answer_spine_default_read" for issue in report["issues"])


def test_presentation_normalization_adds_question_and_cleans_source_labels() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "source_trail": [
            {
                "source_id": "s1",
                "source_label": "Deep Research Flood Sources Outcome Study 2025",
                "appears_in_packet": True,
            },
            {
                "source_id": "s2",
                "source_label": "Deep Research Flood Sources Counter Study 2024",
                "appears_in_packet": True,
            },
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Option A reduced flood losses by 25%.",
                "source_label": "Deep Research Flood Sources Outcome Study 2025",
                "quantities": [{"value": "25%"}],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Option A reduced flood losses by 25% (Deep Research Flood Sources Outcome Study 2025).\n\n"
        "## Sources\n"
        "* Deep Research Flood Sources Outcome Study 2025\n"
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    retention = build_memo_ready_packet_retention_report(result["memo"], packet)

    assert "**Decision question:** Should the city adopt option A?" in result["memo"]
    assert "Outcome Study 2025" in result["memo"]
    assert "Deep Research Flood Sources Outcome Study 2025" not in result["memo"]
    assert result["report"]["status"] == "changed"
    assert retention["missing_mandatory_count"] == 0


def test_presentation_normalization_cleans_source_label_underscore_variants() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "source_trail": [
            {
                "source_id": "s1",
                "source_label": "Deep Research Flood Sources Outcome Study 2025",
                "appears_in_packet": True,
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Option A reduced flood losses by 25%.",
                "source_label": "Deep Research Flood_Sources Outcome Study 2025",
                "source_labels": ["Deep Research Flood_Sources Outcome Study 2025"],
                "quantities": [{"value": "25%"}],
            }
        ],
        "memo_obligations": {
            "obligations": [
                {
                    "obligation_id": "memo_obligation_001",
                    "required": True,
                    "source_labels": ["Deep Research Flood_Sources Outcome Study 2025"],
                    "statement": "Use this support.",
                    "validation_terms": ["support"],
                }
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nOption A reduced flood losses by 25% [Deep Research Flood_Sources Outcome Study 2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "Outcome Study 2025" in result["memo"]
    assert "Deep Research Flood_Sources Outcome Study 2025" not in result["memo"]


def test_presentation_normalization_replaces_model_sources_with_cited_sources() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "source_trail": [
            {"source_id": "s1", "source_label": "Deep Research Flood Sources Outcome Study 2025"},
            {"source_id": "s2", "source_label": "Deep Research Flood Sources Missed Study 2024"},
            {"source_id": "s3", "source_label": "Deep Research Flood Sources Uncited Study 2023"},
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Option A reduced flood losses by 25%.",
                "source_label": "Deep Research Flood Sources Outcome Study 2025",
                "source_labels": ["Deep Research Flood Sources Outcome Study 2025"],
                "quantities": [{"value": "25%"}],
            },
            {
                "item_id": "item_002",
                "must_use": True,
                "role": "strongest_counterweight",
                "reader_claim": "Option A had implementation failures.",
                "source_label": "Deep Research Flood Sources Missed Study 2024",
                "source_labels": ["Deep Research Flood Sources Missed Study 2024"],
            },
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Option A reduced losses by 25% (Deep Research Flood Sources Outcome Study 2025), "
        "but implementation failures remain relevant (Deep Research Flood Sources Missed Study 2024).\n\n"
        "## Sources\n\n"
        "* Outcome Study 2025\n"
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "* Outcome Study 2025" in result["memo"]
    assert "* Missed Study 2024" in result["memo"]
    assert "Uncited Study 2023" not in result["memo"]
    assert result["memo"].count("## Sources") == 1
    assert result["memo"].index("* Outcome Study 2025") < result["memo"].index("* Missed Study 2024")
    assert "deterministic_sources" in result["report"]["changes"]


def test_presentation_normalization_removes_duplicate_decision_heading() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "source_trail": [{"source_id": "s1", "source_label": "Deep Research Flood Sources Outcome Study 2025"}],
        "evidence_items": [],
    }
    memo = "### Decision Brief\n\nOption A is supported [s1]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].count("Decision Brief") == 1
    assert "### Decision Brief" not in result["memo"]
    assert "removed_duplicate_decision_heading" in result["report"]["changes"]


def test_answer_spine_does_not_treat_counterweight_quantity_as_default_support() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    built["decision_briefing_packet"]["answer_frame"]["default_answer"] = (
        "{'classification': 'neutral_or_low_concern_under_stated_conditions'}"
    )
    built["decision_briefing_packet"]["evidence_bundles"].insert(
        0,
        {
            "bundle_id": "bundle_counter_quantity",
            "decision_role": "quantitative_anchor",
            "claim": "Option A had a higher risk of pump failure in poorly maintained sites.",
            "source_ids": ["s2"],
            "source_labels": ["Counter Study"],
            "claim_ids": ["c2"],
            "quantity_values": ["RR 1.40", "95% CI 1.10-1.70"],
            "source_excerpt": "Option A had a higher risk of pump failure (RR 1.40, 95% CI 1.10-1.70).",
            "weight": "high",
            "source_grounded": True,
        },
    )

    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])
    packet = result["memo_ready_packet"]

    assert "{'classification'" in packet["answer_spine"]["default_read"]
    assert "higher risk of pump failure" not in packet["answer_spine"]["default_read"]
    assert any(issue["issue_type"] == "invalid_or_scaffolded_answer_spine_default_read" for issue in result["memo_ready_packet_quality_report"]["issues"])


def test_quantity_binding_preserves_source_local_effect_interval_tuples() -> None:
    packet = {
        "decision_question": "Should the policy treat the exposure as harmful or neutral?",
        "answer_frame": {"default_answer": "The default answer is neutral but bounded.", "confidence": "medium"},
        "source_trail": [{"source_id": "s1", "source_label": "Meta Analysis", "appears_in_packet": True}],
        "evidence_bundles": [
            {
                "bundle_id": "bundle_001",
                "decision_role": "quantitative_anchor",
                "claim": "There is a dose-response relationship where each additional 4 units per week increases risk.",
                "source_ids": ["s1"],
                "source_labels": ["Meta Analysis"],
                "claim_ids": ["c1"],
                "quantity_values": ["RR 2.00", "95% CI 1.02-1.38", "95% CI 1.42-2.37"],
                "source_excerpt": (
                    "The pooled RRs for highest vs lowest intake were 1.19 (95% CI 1.02-1.38), "
                    "1.83 (95% CI 1.42-2.37), and 1.68 (95% CI 1.41-2.00), respectively. "
                    "Subgroup analyses showed higher risk in other countries than the USA "
                    "(RR 2.00, 95% CI 1.14 to 3.51 vs 1.13, 95% CI 0.98 to 1.30)."
                ),
                "weight": "high",
                "source_grounded": True,
            }
        ],
    }

    result = build_quality_synthesis_packet_bundle(packet)
    binding = result["quantity_binding_report"]["bindings"][0]
    tuples = binding["quantity_tuples"]
    rr_200 = next(row for row in tuples if row["estimate"] == "RR 2.00")

    assert rr_200["interval"] == "95% CI 1.14 to 3.51"
    assert all(not (row["estimate"] == "RR 2.00" and row["interval"] == "95% CI 1.02-1.38") for row in tuples)
    assert result["quantity_binding_report"]["unsafe_quantity_pairing_count"] >= 1
    assert all("direction" not in quantity for quantity in binding["quantities"])


def test_quantity_binding_does_not_interpret_unpaired_quantities_directionally() -> None:
    packet = {
        "decision_question": "Should the policy treat the exposure as harmful or neutral?",
        "answer_frame": {"default_answer": "The default answer is neutral but bounded.", "confidence": "medium"},
        "source_trail": [{"source_id": "s1", "source_label": "Meta Analysis", "appears_in_packet": True}],
        "evidence_bundles": [
            {
                "bundle_id": "bundle_001",
                "decision_role": "quantitative_anchor",
                "claim": "The source reports an exposure-outcome association.",
                "source_ids": ["s1"],
                "source_labels": ["Meta Analysis"],
                "claim_ids": ["c1"],
                "quantity_values": ["RR 2.00", "95% CI 1.02-1.38"],
                "source_excerpt": "The source discusses the result elsewhere without a local estimate tuple.",
                "weight": "high",
                "source_grounded": True,
            }
        ],
    }

    result = build_quality_synthesis_packet_bundle(packet)
    binding = result["quantity_binding_report"]["bindings"][0]
    unpaired = [
        quantity
        for quantity in binding["quantities"]
        if quantity.get("binding_warning") == "not_locally_paired_in_source_excerpt"
    ]
    assert unpaired
    assert all("direction" not in quantity for quantity in unpaired)
    assert all("direction, pairing, and effect meaning remain unspecified" in quantity["interpretation"] for quantity in unpaired)


def test_memo_ready_quality_warns_when_default_support_is_missing() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "answer_frame": {"default_answer": "Option A is promising.", "confidence": "medium"},
        "source_trail": [{"source_id": "s2", "source_label": "Counter Study", "appears_in_packet": True}],
        "evidence_bundles": [
            {
                "bundle_id": "bundle_counter",
                "decision_role": "counterweight",
                "claim": "Option A failed when maintenance budgets were cut.",
                "source_ids": ["s2"],
                "source_labels": ["Counter Study"],
                "claim_ids": ["c2"],
                "weight": "high",
                "source_grounded": True,
            }
        ],
    }

    result = build_quality_synthesis_packet_bundle(packet)

    assert any(
        issue["issue_type"] == "missing_strongest_support"
        for issue in result["memo_ready_packet_quality_report"]["issues"]
    )


def test_memo_ready_synthesis_prompt_backend_returns_traceable_draft() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    result = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)
    retention = build_memo_ready_packet_retention_report(result["memo"], packet)

    assert result["report"]["status"] == "deterministic_fallback"
    assert retention["missing_mandatory_count"] == 0
    assert "25%" in result["memo"]
    assert "Counter Study" in result["memo"]


def test_memo_obligations_make_moderate_context_optional() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    decision_packet = built["decision_briefing_packet"]
    decision_packet["source_trail"].append({"source_id": "s4", "source_label": "Context Review"})
    decision_packet["coverage_report"]["truly_lost_moderate_context"] = [
        {
            "candidate_card_id": "ec_context",
            "decision_role": "scope_boundary",
            "priority": 4,
            "source_ids": ["s4"],
            "claim": "Specify the demographic characteristics of the study population.",
        }
    ]

    packet = build_quality_synthesis_packet_bundle(decision_packet)["memo_ready_packet"]
    obligations = packet["memo_obligations"]["obligations"]
    optional = [row for row in obligations if row.get("role") == "source_warning"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    report = build_memo_ready_packet_retention_report(memo, packet)

    assert optional and optional[0]["required"] is False
    assert report["validation_basis"] == "canonical_decision_writer_packet"
    assert report["memo_obligation_count"] >= len(obligations)
    assert report["unresolved_warning_count"] == 0


def test_obligation_repair_prompt_excludes_optional_warning_repairs() -> None:
    packet = {
        "decision_question": "Should the city adopt option A?",
        "memo_obligations": {
            "obligations": [
                {
                    "obligation_id": "memo_obligation_001",
                    "required": True,
                    "obligation_type": "must_weigh_support",
                    "role": "strongest_support",
                    "statement": "Use support for option A.",
                    "source_labels": ["Outcome Study"],
                    "quantities": [],
                }
            ]
        },
        "memo_warning_packet": {
            "warnings": [
                {
                    "warning_id": "memo_warning_001",
                    "severity": "moderate",
                    "warning_type": "omitted_moderate_context",
                    "claim": "Specify demographic characteristics.",
                    "source_labels": ["Context Study"],
                }
            ]
        },
    }
    retention = {
        "validation_basis": "memo_obligations",
        "issues": [
            {
                "issue_type": "missing_memo_obligation",
                "obligation_id": "memo_obligation_001",
                "obligation_type": "must_weigh_support",
            }
        ],
        "warning_resolution_report": {
            "warnings_needing_repair": [
                {
                    "warning_id": "memo_warning_001",
                    "status": "possibly_addressed",
                    "missing_anchor_terms": ["demographic"],
                }
            ]
        },
    }

    prompt = build_memo_ready_packet_repair_prompt("## Decision Brief\n\nOption A may help.", packet, retention)

    assert "missing_obligations" in prompt
    assert '"unresolved_warnings": []' in prompt
    assert "Specify demographic characteristics" not in prompt


def test_memo_obligation_statements_sanitize_artifact_and_overclaim_language() -> None:
    packet = build_memo_obligation_packet(
        [
            {
                "item_id": "crux_001",
                "must_use": True,
                "role": "decision_crux",
                "reader_claim": (
                    "Cholesterol intake is the primary driver of risk. crux for daily egg consumption. "
                    "These findings are consistently neutralized."
                ),
                "source_label": "Crux Study",
                "source_labels": ["Crux Study"],
            }
        ],
        {"warnings": []},
    )
    statement = packet["obligations"][0]["statement"].lower()

    assert "crux for" not in statement
    assert "primary driver" not in statement
    assert "consistently neutralized" not in statement
    assert "potentially important driver" in statement


def test_scope_obligation_does_not_force_raw_demographic_quantities() -> None:
    item = {
        "item_id": "scope_001",
        "must_use": True,
        "role": "scope_boundary",
        "reader_claim": "RESULTS: 140 patients were randomized; median age 66 years; 51% women; 24% with diabetes mellitus.",
        "source_label": "Population Study",
        "source_labels": ["Population Study"],
        "quantities": [{"value": "51%"}, {"value": "24%"}],
    }
    packet = {
        "decision_question": "Should the city adopt option A?",
        "evidence_items": [item],
        "memo_obligations": build_memo_obligation_packet([item], {"warnings": []}),
        "memo_warning_packet": {"warnings": []},
        "source_trail": [{"source_label": "Population Study", "appears_in_packet": True}],
    }
    memo = (
        "## Decision Brief\n\n"
        "The answer applies to the studied population and should not be generalized beyond that scope.\n\n"
        "## Sources\n\n"
        "* Population Study\n"
    )

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["status"] == "ready"
    assert report["missing_quantity_count"] == 0
    assert report["missing_evidence_item_count"] == 1


def test_warning_resolution_report_flags_unresolved_warning_evidence() -> None:
    warning_packet = {
        "warnings": [
            {
                "warning_id": "memo_warning_001",
                "warning_type": "omitted_decision_critical_evidence",
                "severity": "critical",
                "source_labels": ["Equity Review"],
                "claim": "Option A shifted flood risk toward downstream neighborhoods.",
                "anchor_terms": ["shifted", "downstream", "neighborhoods"],
            }
        ]
    }

    unresolved = build_warning_resolution_report("## Decision Brief\n\nOption A has strong support.", warning_packet)
    addressed = build_warning_resolution_report(
        "## Decision Brief\n\nEquity Review warns that Option A shifted flood risk toward downstream neighborhoods.",
        warning_packet,
    )

    assert unresolved["unresolved_count"] == 1
    assert addressed["unresolved_count"] == 0
    assert addressed["addressed_count"] == 1


def test_memo_ready_synthesis_fallback_renders_all_bound_quantities() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    item = next(item for item in packet["evidence_items"] if item["role"] == "quantitative_anchor")
    item["quantities"].extend(
        [
            {"value": "10 years", "interpretation": "follow-up duration"},
            {"value": "4 sites", "interpretation": "applicability breadth"},
            {"value": "1,200 participants", "interpretation": "sample size"},
        ]
    )

    result = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)

    assert "10 years" in result["memo"]
    assert "4 sites" in result["memo"]
    assert "1,200 participants" in result["memo"]


def test_memo_ready_synthesis_fallback_renders_structured_spine_text() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    packet["answer_spine"]["default_read"] = {
        "classification": "conditional_support",
        "current_read": "Option A is promising if maintenance funding is protected.",
    }

    result = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)

    assert "Option A is promising if maintenance funding is protected." in result["memo"]
    assert "{'classification'" not in result["memo"]


def test_memo_ready_retention_report_flags_missing_source_and_quantity() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    report = build_memo_ready_packet_retention_report("## Decision Brief\n\nOption A may help.\n", packet)

    assert report["status"] == "warning"
    assert report["missing_mandatory_count"] >= 1
    assert report["missing_quantity_count"] >= 1


def test_memo_ready_repair_accepts_retention_improvement(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    weak_memo = "## Decision Brief\n\nOption A may help.\n"
    before = build_memo_ready_packet_retention_report(weak_memo, packet)
    repaired = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=repaired, backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_repair(weak_memo, packet, before, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert "25%" in result["memo"]
    assert "Counter Study" in result["memo"]


def test_memo_ready_repair_accepts_warning_resolution(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    decision_packet = built["decision_briefing_packet"]
    decision_packet["source_trail"].append({"source_id": "s4", "source_label": "Equity Review"})
    decision_packet["coverage_report"]["truly_lost_decision_critical"] = [
        {
            "candidate_card_id": "ec_warning",
            "decision_role": "counterweight",
            "priority": 10,
            "source_ids": ["s4"],
            "claim": "Option A shifted flood risk toward downstream neighborhoods.",
        }
    ]
    packet = build_quality_synthesis_packet_bundle(decision_packet)["memo_ready_packet"]
    weak_memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    before = build_memo_ready_packet_retention_report(weak_memo, packet)
    repaired = weak_memo.replace(
        "## Sources",
        "The Equity Review adds an important limitation: Option A shifted flood risk toward downstream neighborhoods.\n\n## Sources",
    )

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=repaired, backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_repair(weak_memo, packet, before, backend="fake", backend_timeout=30, backend_retries=0)

    assert before["unresolved_warning_count"] == 0
    assert any(issue["issue_type"] == "missing_memo_obligation" for issue in before["issues"])
    assert result["report"]["status"] == "accepted"
    assert result["report"]["final_missing_mandatory_count"] == 0
    assert "Equity Review" in result["memo"]


def test_memo_ready_final_polish_rejects_evidence_loss(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text="## Decision Brief\n\nOption A may help.\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_json_final_polish_experiment(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "json_edit_parse_failed_kept_original"
    assert result["memo"] == memo


def test_memo_ready_final_polish_prompt_treats_protected_items_as_constraints() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    prompt = build_memo_ready_final_polish_prompt("## Decision Brief\n\nOption A may help.", packet)

    assert "Return JSON edits, not a rewritten memo" in prompt
    assert "Each target_text must be copied exactly" in prompt
    assert "Prefer one or two high-value paragraph-level edits" in prompt
    assert "paragraph-level edits" in prompt
    assert "decision-ready analysis written for a thoughtful human judge" in prompt
    assert "evidence-weighted reasoning" in prompt
    assert "citation clutter" in prompt
    assert "Return valid JSON only" in prompt
    assert "unsupported_side_point" in prompt
    assert "Current prose diagnostics" in prompt
    assert "memo_prose_quality_diagnostics_v1" in prompt
    assert "Validation guardrails" in prompt
    assert "memo_ready_final_polish_guardrails_v1" in prompt
    assert "source_ids_that_must_remain_traceable" in prompt
    assert "quantities_that_must_remain_visible" in prompt
    assert "scope_or_counterweight_cues_to_preserve" in prompt
    assert "protected_anchor_checklist" not in prompt
    assert "legacy_mandatory_items" not in prompt


def test_memo_ready_final_polish_normalizes_safe_citation_and_phrase_defects(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]
    payload = {
        "edits": [
            {
                "target_text": "## Sources",
                "replacement_text": (
                    "The primary support for this conclusion stems from Outcome Study: Option A reduced flood losses "
                    "by 25% in comparable river cities (Zhong etal. 2019).\n\n## Sources"
                ),
                "reason": "smooth source setup",
                "intended_improvement": "clarity",
            }
        ]
    }

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text=json.dumps(payload), backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_json_final_polish_experiment(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert result["report"]["accepted_edit_count"] == 1
    assert "The main support is" in result["memo"]
    assert "etal." not in result["memo"]


def test_memo_ready_polish_cleanup_is_narrow() -> None:
    cleaned = normalize_memo_ready_polish_text(
        "## Decision Brief\n\nThe primary support for this neutral stance is rooted in Zhong etal. 2019 reporting 0.93.\n"
    )

    assert "The main support for this neutral stance is Zhong et al. 2019 reporting 0.93." in cleaned


def test_memo_ready_polish_softens_overconfident_stock_phrases() -> None:
    cleaned = normalize_memo_ready_polish_text(
        "## Decision Brief\n\n"
        "**Answer Stance:** Neutral (Safe for moderate consumption)\n\n"
        "The option is considered neutral and safe. High-confidence data from large-scale cohort studies establish "
        "a safe limit, so the safety profile is settled. One serving is considered safe. "
        "This creates a baseline of safety and a safe standard. Dietary guidance can safely include the option. "
        "The association is fully accounted for by implementation conditions, independent of context, and does not harm heart health.\n"
    )

    assert "best treated as neutral within the stated scope" in cleaned
    assert "evidence from large-scale cohort studies" in cleaned
    assert "practical reference point" in cleaned
    assert "evidence-bounded reference point" in cleaned
    assert "risk profile" in cleaned
    assert "safe limit" not in cleaned
    assert "considered safe" not in cleaned
    assert "baseline of safety" not in cleaned
    assert "safe standard" not in cleaned
    assert "High-confidence data" not in cleaned
    assert "safely include" not in cleaned
    assert "fully accounted for" not in cleaned
    assert "independent of" not in cleaned
    assert "does not harm heart health" not in cleaned
    assert "may be partly accounted for by implementation conditions" in cleaned
    assert "not fully explained by context" in cleaned
    assert "does not clearly show higher cardiovascular risk in the stated scope" in cleaned
    assert "Neutral (Neutral for moderate consumption)" not in cleaned
    assert "Neutral for moderate consumption" in cleaned


def test_final_reader_outputs_use_memo_ready_packet_path(tmp_path: Path) -> None:
    scaffold = _scaffold()
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"]))
    scaffold.update(build_quality_synthesis_packet_bundle(scaffold["decision_briefing_packet"]))

    result = write_final_reader_outputs(
        rendered="## Decision Brief\n\nSeed memo.",
        scaffold=scaffold,
        prioritized_map={"claims": []},
        artifacts=tmp_path,
        backend_config=ModelBackendConfig(backend="prompt", timeout=30, retries=0),
    )

    paths = result["summary_paths"]
    assert result["rewrite_result"]["report"]["memo_ready_packet_path"] is True
    assert paths["memo_ready_synthesis_report"].exists()
    assert paths["memo_ready_synthesis_prompt"].exists()
    assert paths["memo_ready_repair_report"].exists()
    assert paths["memo_ready_final_polish_report"].exists()
    assert paths["citation_trace"].exists()
    assert paths["canonical_decision_writer_packet"].exists()
    assert paths["canonical_decision_writer_packet_quality_report"].exists()
    assert paths["source_weight_judgment_report"].exists()
    assert paths["argument_spine_quality_report"].exists()
    assert paths["canonical_writer_prompt_context_audit"].exists()
    assert json.loads(paths["source_weight_judgment_report"].read_text(encoding="utf-8"))["schema_id"] == "source_weight_judgment_report_v1"
    assert json.loads(paths["argument_spine_quality_report"].read_text(encoding="utf-8"))["schema_id"] == "argument_spine_quality_report_v1"
    prompt_audit = json.loads(paths["canonical_writer_prompt_context_audit"].read_text(encoding="utf-8"))
    assert prompt_audit["status"] == "pass"
    assert "Inline memo citations link here" in paths["citation_trace"].read_text(encoding="utf-8")
    assert paths["memo_creation_progress"].exists()
    progress = [
        json.loads(line)
        for line in paths["memo_creation_progress"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stages = [row["stage"] for row in progress]
    assert "memo_ready_synthesis" in stages
    assert "memo_ready_final_polish" in stages
    assert progress[-1]["status"] == "completed"
    assert "25%" in result["briefing_path"].read_text()


def test_final_reader_outputs_require_memo_ready_packet(tmp_path: Path) -> None:
    scaffold = _scaffold()

    with pytest.raises(ValueError, match="memo_ready_packet.evidence_items"):
        write_final_reader_outputs(
            rendered="## Decision Brief\n\nSeed memo.",
            scaffold=scaffold,
            prioritized_map={"claims": []},
            artifacts=tmp_path,
            backend_config=ModelBackendConfig(backend="prompt", timeout=30, retries=0),
        )

    progress_path = tmp_path / "memo_creation_progress.jsonl"
    progress = [
        json.loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert progress[-1]["status"] == "failed_missing_memo_ready_packet"


def test_pipeline_simplification_comparison_summarizes_completion_audit() -> None:
    scaffold = _scaffold()
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"]))
    scaffold.update(build_quality_synthesis_packet_bundle(scaffold["decision_briefing_packet"]))
    final_outputs = {
        "rewrite_result": {"report": {"memo_ready_packet_path": True, "status": "memo_ready_synthesis_deterministic_fallback"}},
        "diagnostics": {
            "packet_retention": {"status": "ready", "must_retain_count": 3, "retained_must_retain_count": 3},
            "source_lineage": {"status": "ready", "matched_source_count": 3, "expected_source_count": 3},
            "runtime_budget": {"model_call_count": 1, "stages": [{"stage": "reader_memo_rewrite"}]},
            "final_eval": {"status": "ready"},
            "memo_coherence": {"status": "ready"},
        },
        "summary_paths": {"section_rewrite_report": Path("section_rewrite_report.json")},
    }

    report = build_pipeline_simplification_comparison(
        scaffold=scaffold,
        final_outputs=final_outputs,
        briefing_path="BRIEFING.md",
        evidence_appendix_path="EVIDENCE_APPENDIX.md",
    )

    assert report["schema_id"] == "pipeline_simplification_comparison_v1"
    assert report["synthesis_path"] == "memo_ready_packet"
    assert report["retention_metrics"]["retained_must_retain_count"] == 3
    assert report["provenance_lineage_completeness"]["claim_lineage_coverage"] >= 0.9
