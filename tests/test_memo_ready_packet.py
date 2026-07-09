from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_final_outputs import ModelBackendConfig, write_final_reader_outputs
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_memo_ready_packet_retention_report,
    run_memo_ready_final_polish,
    run_memo_ready_packet_repair,
    run_memo_ready_packet_synthesis,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import (
    build_memo_ready_packet_synthesis_prompt,
    build_quality_synthesis_packet_bundle,
)
from epistemic_case_mapper.map_briefing_simplification_comparison import build_pipeline_simplification_comparison
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


def test_synthesis_prompt_uses_memo_ready_packet_not_legacy_section_contract() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    result = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])

    prompt = build_memo_ready_packet_synthesis_prompt(result["memo_ready_packet"])

    assert "memo-ready evidence packet" in prompt
    assert "Why This Read" not in prompt
    assert "Evidence Carrying the Conclusion" not in prompt
    assert "25%" in prompt
    assert "Counter Study" in prompt


def test_memo_ready_packet_replaces_malformed_generic_default_read() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    built["decision_briefing_packet"]["answer_frame"]["default_answer"] = (
        "{'classification': 'neutral_or_low_concern_under_stated_conditions', "
        "'current_read': 'State the default as neutral or low-concern under the stated conditions.'..."
    )

    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    assert "{'classification'" not in packet["answer_spine"]["default_read"]
    assert "Option A" in packet["answer_spine"]["default_read"]


def test_memo_ready_synthesis_prompt_backend_returns_traceable_draft() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    result = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)
    retention = build_memo_ready_packet_retention_report(result["memo"], packet)

    assert result["report"]["status"] == "deterministic_fallback"
    assert retention["missing_mandatory_count"] == 0
    assert "25%" in result["memo"]
    assert "Counter Study" in result["memo"]


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

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_repair(weak_memo, packet, before, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert "25%" in result["memo"]
    assert "Counter Study" in result["memo"]


def test_memo_ready_final_polish_rejects_evidence_loss(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    memo = run_memo_ready_packet_synthesis(packet, backend="prompt", backend_timeout=30, backend_retries=0)["memo"]

    def fake_backend(*args, **kwargs) -> ModelBackendResult:
        return ModelBackendResult(text="## Decision Brief\n\nOption A may help.\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_final_polish(memo, packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "rejected_kept_original"
    assert result["memo"] == memo


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
    assert "25%" in result["briefing_path"].read_text()


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
