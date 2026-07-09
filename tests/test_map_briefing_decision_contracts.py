from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.map_briefing import (
    adaptive_briefing_claim_budget,
    append_evidence_by_decision_lever,
    append_map_coverage_snapshot,
    annotate_map_with_evidence_slots,
    briefing_scaffold,
    build_crux_contract,
    build_briefing_contract,
    build_map_briefing_prompt,
    build_decision_model,
    build_decision_slots,
    build_concept_evidence_packets,
    build_decision_memo_slots,
    build_evidence_compression_table,
    build_evidence_slot_ledger,
    build_evidence_weighting_ledger,
    build_map_sufficiency_report,
    build_option_comparison,
    build_reader_memo_rewrite_contract,
    build_proposition_clusters,
    build_curated_evidence_packets,
    calibrate_confidence,
    briefing_reader_polish_report,
    clean_reader_briefing_text,
    compose_final_reader_memo_package,
    expand_reader_map_references,
    model_parse_diagnostics,
    partition_map_evidence,
    polish_briefing_for_reader,
    prioritize_map_for_briefing,
    repair_briefing_payload,
    repair_reader_memo_rewrite_candidate,
    reader_memo_rewrite_issues,
    run_map_briefing,
    validate_briefing_against_scaffold,
    _rewrite_mentions_anchor_row,
)
from epistemic_case_mapper.staged_semantic_pipeline import CLAIM_EXTRACTION_PROMPT_VERSION, RELATION_PROMPT_VERSION


def test_decision_model_clusters_claims_into_neutral_default_with_subgroup_caution() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Moderate use was not associated with worse long-term outcomes in generally healthy adults.",
                "source_id": "cohort_full",
                "source_span": "lines 1-1",
                "excerpt": "Moderate use was not associated with worse long-term outcomes in generally healthy adults.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "High use was associated with higher risk in people with a pre-existing condition.",
                "source_id": "subgroup_full",
                "source_span": "lines 1-1",
                "excerpt": "High use was associated with higher risk in people with a pre-existing condition.",
                "entailed_by_excerpt": "yes",
                "role": "scope_limit",
            },
            {
                "claim_id": "c003",
                "claim": "The trial measured a biomarker rather than hard outcome events.",
                "source_id": "trial_full",
                "source_span": "lines 1-1",
                "excerpt": "The trial measured a biomarker rather than hard outcome events.",
                "entailed_by_excerpt": "yes",
                "role": "measurement_validity",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "in_tension_with",
                "rationale": "The subgroup risk limits how broadly the neutral general-population finding should be applied.",
            }
        ],
    }
    source_lookup = {"cohort_full": "Cohort Full", "subgroup_full": "Subgroup Full", "trial_full": "Trial Full"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    contract = build_briefing_contract(partition, quality_report)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    clusters = build_proposition_clusters(candidate_map, ledger, source_lookup)
    decision_model = build_decision_model(clusters, contract, quality_report)

    assert clusters["cluster_count"] >= 2
    assert decision_model["default_answer"]["classification"] == "neutral_or_low_concern_under_stated_conditions"
    assert decision_model["main_reasons"]
    assert decision_model["strongest_counterarguments"]
    assert any("Do not" in item or "Avoid" in item for item in decision_model["prose_requirements"])


def test_decision_model_lint_softens_benefit_framing_for_neutral_default() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was not associated with worse outcomes.",
                "source_id": "trial",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "High-intensity use was associated with higher risk in one subgroup.",
                "source_id": "cohort",
                "role": "scope_limit",
            },
        ],
        "relations": [],
    }
    source_lookup = {"trial": "Trial", "cohort": "Cohort"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "The intervention is associated with potentially lower long-term risk in the default case.",
        "confidence": "medium",
        "decision_implications": ["Treat it as a beneficial default."],
        "evidence_roles": {"main_support": [], "conflicting_evidence": [], "scope_limits": [], "method_limits": []},
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup, candidate_map)

    joined = json.dumps(repaired).lower()
    assert "potentially lower" not in joined
    assert "beneficial default" not in joined
    assert "neutral or low-concern" in joined


def test_repair_briefing_payload_applies_contract_lint_to_final_prose() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was not associated with worse outcomes.",
                "source_id": "trial",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"trial": "Trial"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 88, "issues": [{"severity": "risk", "issue_type": "limited_followup"}]},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "The intervention is neutral to potentially beneficial and clearly safe.",
        "confidence": "high",
        "decision_implications": ["Patients can safely use it."],
        "evidence_roles": {"main_support": [], "conflicting_evidence": [], "scope_limits": [], "method_limits": []},
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup, candidate_map)

    joined = json.dumps(repaired)
    assert "potentially beneficial" not in joined
    assert "clearly safe" not in joined
    assert "low-concern under the stated conditions" in repaired["decision_brief"]


def test_expand_reader_map_references_removes_short_claim_ids() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "school_hepa_priority_c026",
                "claim": "HEPA classrooms had lower PM 2.5 than comparison classrooms.",
                "source_id": "trial",
            },
            {
                "claim_id": "school_hepa_priority_c029",
                "claim": "The health benefit of the small PM reduction remains unclear.",
                "source_id": "trial",
            },
        ],
        "relations": [
            {
                "relation_id": "school_hepa_priority_r001",
                "source_claim": "school_hepa_priority_c029",
                "target_claim": "school_hepa_priority_c026",
                "relation_type": "in_tension_with",
                "rationale": "Claim c029 limits the interpretation of Claim c026.",
            }
        ],
    }

    expanded = expand_reader_map_references(
        "Claim c026 supports the intervention, but Claim C029 limits it. Supported by trial (c026). Relation r001 matters.",
        candidate_map,
    )

    assert "Claim c026" not in expanded
    assert "Claim C029" not in expanded
    assert "(c026)" not in expanded
    assert "Relation r001" not in expanded
    assert "the mapped claim that" not in expanded
    assert "HEPA classrooms had lower PM 2.5" in expanded
    assert "This supports the intervention" in expanded
    assert "health benefit of the small PM reduction remains unclear" in expanded


def test_run_map_briefing_renders_readable_packet_without_raw_source_ids(tmp_path: Path) -> None:
    map_path = tmp_path / "generated_map.json"
    quality_path = tmp_path / "map_quality_report.json"
    map_path.write_text(
        json.dumps(
            {
                "title": "COVID map",
                "sources": ["flf_covid_case_brief"],
                "claims": [
                    {
                        "claim_id": "covid_c001",
                        "claim": "The case turns on whether priors or likelihood updates explain the disagreement.",
                        "source_id": "flf_covid_case_brief",
                        "source_span": "lines 1-2",
                        "excerpt": "Priors and likelihoods both matter.",
                        "entailed_by_excerpt": "yes",
                        "role": "crux",
                    }
                ],
                "relations": [],
            }
        ),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps(
            {
                "status": "usable_with_review",
                "score": 90,
                "summary": {"claim_count": 1, "relation_count": 0},
                "issues": [{"severity": "risk", "issue_type": "low_relation_type_diversity", "message": "Few relations."}],
            }
        ),
        encoding="utf-8",
    )
    fake_model = tmp_path / "fake_briefing_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({\n"
        "  'decision_brief': 'flf_covid_case_brief says the decision depends on priors and likelihood updates.',\n"
        "  'confidence': 'high',\n"
        "  'decision_implications': ['Use flf_covid_case_brief as a crux source, not a settled conclusion.'],\n"
        "  'top_cruxes': [{'crux': 'covid_c001', 'why_it_matters': 'It controls interpretation.', 'current_read': 'Mixed.', 'would_change_if': 'New evidence separated priors from likelihoods.'}],\n"
        "  'evidence_roles': {'main_support': [], 'conflicting_evidence': [], 'scope_limits': ['flf_covid_case_brief has a scope boundary.'], 'method_limits': []},\n"
        "  'stress_caveats': [],\n"
        "  'audit_trail': ['Claim A states that covid_c001 matters while Claim B is missing.']\n"
        "}))\n",
        encoding="utf-8",
    )
    baseline_path = tmp_path / "deep_research_baseline.md"
    baseline_path.write_text(
        "A polished baseline also discusses PROSPERITY trial evidence, Carter 2025, and DIABEGG.",
        encoding="utf-8",
    )

    result = run_map_briefing(
        repo_root=tmp_path,
        map_path=map_path,
        quality_report_path=quality_path,
        question="What should a decision-maker conclude?",
        backend=f"command:{sys.executable} {fake_model}",
        output_dir=tmp_path / "briefing",
        source_titles={"flf_covid_case_brief": "FLF COVID Case Brief"},
        baseline_path=baseline_path,
    )

    rendered = result.briefing_path.read_text(encoding="utf-8")
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    sufficiency = json.loads(result.sufficiency_report_path.read_text(encoding="utf-8"))
    validation = json.loads(result.briefing_validation_path.read_text(encoding="utf-8"))
    telemetry = json.loads(result.gap_diagnosis_path.read_text(encoding="utf-8"))
    assert "**Confidence:** medium" in rendered
    assert "flf_covid_case_brief" not in rendered
    assert "FLF COVID Case Brief" in rendered
    assert "The case turns on whether priors or likelihood updates explain the disagreement" in rendered
    assert "Claim A" not in rendered
    assert "Claim B" not in rendered
    assert "mapped claim" not in rendered
    assert "source-grounded finding" not in rendered
    assert summary["model_confidence"] == "not specified"
    assert summary["calibrated_confidence"] == "medium"
    assert summary["paths"]["map_sufficiency_report"].endswith("map_sufficiency_report.json")
    assert summary["paths"]["source_evidence_cards"].endswith("source_evidence_cards.json")
    assert summary["paths"]["source_sufficiency_report"].endswith("source_sufficiency_report.json")
    assert summary["paths"]["evidence_quality_report"].endswith("evidence_quality_report.json")
    assert summary["paths"]["section_context_acceptance_report"].endswith("section_context_acceptance_report.json")
    assert summary["paths"]["memo_coherence_report"].endswith("memo_coherence_report.json")
    assert summary["paths"]["pipeline_migration_ledger"].endswith("pipeline_migration_ledger.json")
    assert summary["paths"]["runtime_budget_report"].endswith("runtime_budget_report.json")
    assert summary["paths"]["final_brief_evaluation"].endswith("final_brief_evaluation.json")
    assert summary["paths"]["scoped_metric_report"].endswith("scoped_metric_report.json")
    assert summary["paths"]["final_source_lineage_report"].endswith("final_source_lineage_report.json")
    assert summary["paths"]["pipeline_measurement_audit"].endswith("pipeline_measurement_audit.json")
    assert summary["paths"]["pipeline_simplification_comparison"].endswith("pipeline_simplification_comparison.json")
    assert (tmp_path / summary["paths"]["pipeline_simplification_comparison"]).exists()
    assert summary["source_evidence_card_count"] == 1
    assert summary["source_sufficiency_status"] in {
        "sufficient_for_decision_ready_answer",
        "sufficient_for_bounded_answer",
        "insufficient_source_set",
    }
    assert isinstance(summary["source_sufficiency_missing_categories"], list)
    assert isinstance(summary["evidence_quality_weak_or_indirect_count"], int)
    assert summary["section_context_acceptance_status"] in {"ready", "warning", "not_synthesis_ready"}
    assert summary["memo_coherence_report_path"].endswith("memo_coherence_report.json")
    assert summary["runtime_budget_report_path"].endswith("runtime_budget_report.json")
    assert summary["final_brief_evaluation_path"].endswith("final_brief_evaluation.json")
    assert summary["paths"]["briefing_validation_report"].endswith("briefing_validation_report.json")
    assert summary["paths"]["gap_diagnosis"].endswith("telemetry/gap_diagnosis.json")
    assert sufficiency["schema_id"] == "map_sufficiency_report_v1"
    assert validation["schema_id"] == "briefing_validation_report_v1"
    assert summary["briefing_validation_status"] == validation["status"]
    assert telemetry["schema_id"] == "map_briefing_gap_telemetry_v1"
    assert telemetry["baseline_gap_attribution"]["baseline_available"] is True
    assert "crux_quality" in telemetry["relation_quality"]
    assert telemetry["largest_gap_drivers"]
    assert any("PROSPERITY" in term for term in telemetry["baseline_gap_attribution"]["salient_baseline_terms_absent"])


def test_synthesize_map_briefing_cli(monkeypatch, tmp_path: Path) -> None:
    map_path = tmp_path / "map.json"
    quality_path = tmp_path / "quality.json"
    map_path.write_text(
        json.dumps(
            {
                "sources": ["doc_a"],
                "claims": [{"claim_id": "demo_c001", "claim": "Alpha matters.", "source_id": "doc_a", "role": "crux"}],
                "relations": [],
            }
        ),
        encoding="utf-8",
    )
    quality_path.write_text(json.dumps({"status": "needs_repair", "score": 50, "issues": []}), encoding="utf-8")
    fake_model = tmp_path / "fake_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'decision_brief': 'doc_a says Alpha matters.', 'confidence': 'high', 'decision_implications': [], 'top_cruxes': [], 'evidence_roles': {'main_support': [], 'conflicting_evidence': [], 'scope_limits': [], 'method_limits': []}, 'stress_caveats': [], 'audit_trail': []}))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "missing_manifest_but_prompt_backend_needs_default.yaml",
            "synthesize",
            "map-briefing",
            "--map",
            str(map_path),
            "--quality-report",
            str(quality_path),
            "--question",
            "What follows?",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    (tmp_path / "missing_manifest_but_prompt_backend_needs_default.yaml").write_text(
        "package_label: Demo\ncases: []\nworked_regions: []\ndefault_model_backend: prompt\n",
        encoding="utf-8",
    )

    assert cli.main() == 0
    rendered = (tmp_path / "out/BRIEFING.md").read_text(encoding="utf-8")
    rewrite_report = json.loads((tmp_path / "out/reader_memo_rewrite_report.json").read_text(encoding="utf-8"))
    assert "**Confidence:** low" in rendered
    assert "doc_a" not in rendered
    assert "Doc A" in rendered
    assert rewrite_report["status"] != "skipped_after_section_rewrite"
    assert rewrite_report["pass_count"] >= 1


def test_semantic_staged_brief_cli_runs_full_path(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    decision_question = "Should this demo decision rely on Alpha or Gamma?"
    fake_model = tmp_path / "fake_staged_brief_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    if 'Source ID: demo_case_doc_a' in prompt:\n"
        "        payload = {'claims': [{'claim': 'Alpha supports the decision.', 'span_id': 'demo_case_doc_a_s0001', 'entailed_by_excerpt': 'yes', 'role': 'conclusion_support'}]}\n"
        "    else:\n"
        "        payload = {'claims': [{'claim': 'Gamma is the key crux.', 'span_id': 'demo_case_doc_b_s0001', 'entailed_by_excerpt': 'yes', 'role': 'crux'}]}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {'pair_id': 'pair_001', 'source_claim': 'demo_case_c002', 'target_claim': 'demo_case_c001', 'relation_type': 'crux_for', 'rationale': 'Gamma changes whether Alpha should guide the decision.', 'crux_candidates': ['Gamma is a crux.'], 'similar_but_not_identical': []}\n"
        "elif 'Deterministic briefing scaffold:' in prompt:\n"
        "    payload = {'decision_brief': 'Demo Case Doc A and Demo Case Doc B jointly make Gamma the crux.', 'confidence': 'high', 'decision_implications': ['Treat Gamma as the first review target.'], 'top_cruxes': [], 'evidence_roles': {'main_support': [], 'conflicting_evidence': [], 'scope_limits': [], 'method_limits': []}, 'stress_caveats': [], 'audit_trail': []}\n"
        "else:\n"
        "    payload = {}\n"
        "print(json.dumps(payload))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "semantic",
            "staged",
            "brief",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--claim-extractor",
            "native",
            "--question",
            decision_question,
            "--briefing-dir",
            str(tmp_path / "brief"),
            "--artifact-dir",
            str(tmp_path / "map_artifacts"),
            "--output",
            str(tmp_path / "generated_map.json"),
            "--backend-retries",
            "0",
        ],
    )

    assert cli.main() == 0
    assert (tmp_path / "generated_map.json").exists()
    rendered = (tmp_path / "brief/BRIEFING.md").read_text(encoding="utf-8")
    assert "## Decision Brief" in rendered
    assert "Doc A" in rendered
    assert "Alpha supports the decision" in rendered
    assert "demo_case_doc_a" not in rendered
    run_summary = json.loads((tmp_path / "map_artifacts/run_summary.json").read_text(encoding="utf-8"))
    claim_prompt = next((tmp_path / "map_artifacts/claim_chunks").glob("*_prompt.txt")).read_text(encoding="utf-8")
    assert run_summary["decision_question"] == decision_question
    assert f"Decision question: {decision_question}" in claim_prompt


def _init_demo_case(monkeypatch, tmp_path: Path) -> None:
    doc_a = tmp_path / "doc_a.txt"
    doc_b = tmp_path / "doc_b.txt"
    doc_a.write_text("Alpha line.\nBeta line.\n", encoding="utf-8")
    doc_b.write_text("Gamma line.\nDelta line.\n", encoding="utf-8")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "case",
            "init",
            "--case-id",
            "demo_case",
            "--title",
            "Demo Case",
            "--question",
            "Can this package be initialized from arbitrary docs?",
            "--docs",
            str(doc_a),
            str(doc_b),
        ],
    )
    assert cli.main() == 0
