from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.map_briefing import (
    briefing_scaffold,
    calibrate_confidence,
    expand_reader_map_references,
    prioritize_map_for_briefing,
    repair_briefing_payload,
    run_map_briefing,
)
from epistemic_case_mapper.staged_semantic_pipeline import CLAIM_EXTRACTION_PROMPT_VERSION, RELATION_PROMPT_VERSION


def test_confidence_calibration_caps_high_when_map_has_risks() -> None:
    report = {
        "status": "usable_with_review",
        "score": 90,
        "issues": [{"severity": "risk", "issue_type": "high_claim_count", "message": "Dense map."}],
    }

    calibrated = calibrate_confidence("high", report)

    assert calibrated["calibrated_confidence"] == "medium"
    assert "risk_issue_caps_high_confidence" in calibrated["reasons"]


def test_prioritization_preserves_source_coverage() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c001", "claim": "A crux.", "source_id": "source_a", "role": "crux"},
            {"claim_id": "c002", "claim": "A support.", "source_id": "source_a", "role": "conclusion_support"},
            {"claim_id": "c003", "claim": "B scope.", "source_id": "source_b", "role": "scope_limit"},
            {"claim_id": "c004", "claim": "C background.", "source_id": "source_c", "role": "background"},
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c001",
                "target_claim": "c003",
                "relation_type": "crux_for",
                "rationale": "The crux determines whether the scope limit matters.",
            }
        ],
    }

    prioritized, report = prioritize_map_for_briefing(candidate_map, quality_report={"status": "usable_with_review"}, max_claims=3)

    assert report["changed"] is True
    assert report["ranking_method"] == "source_coverage_then_role_priority_weighted_pagerank_with_tfidf_duplicate_suppression"
    assert report["source_coverage_preserved"] is True
    assert report["centrality_scores"]["c001"] > 0
    assert {claim["source_id"] for claim in prioritized["claims"]} == {"source_a", "source_b", "source_c"}
    assert "c002" in report["dropped_claim_ids"]


def test_prioritization_reports_tfidf_duplicate_pairs() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The trial measured LDL cholesterol biomarkers rather than cardiovascular events.",
                "source_id": "source_a",
                "role": "crux",
            },
            {
                "claim_id": "c002",
                "claim": "The trial measured LDL biomarkers instead of cardiovascular event outcomes.",
                "source_id": "source_a",
                "role": "crux",
            },
            {
                "claim_id": "c003",
                "claim": "Guideline policy judgment uses a broader evidence process.",
                "source_id": "source_b",
                "role": "scope_limit",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c001",
                "target_claim": "c003",
                "relation_type": "crux_for",
                "rationale": "Endpoint interpretation changes the policy read.",
            }
        ],
    }

    _prioritized, report = prioritize_map_for_briefing(
        candidate_map,
        quality_report={"status": "usable_with_review"},
        max_claims=2,
    )

    pairs = {(row["left"], row["right"]) for row in report["duplicate_claim_pairs"]}
    assert ("c001", "c002") in pairs
    assert report["centrality_scores"]["c001"] > report["centrality_scores"]["c002"]


def test_repair_briefing_payload_replaces_source_only_evidence_roles() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Portable cleaners should be supplemental when targeted filtration is needed.",
                "source_id": "epa_school",
                "role": "crux",
            },
            {
                "claim_id": "c002",
                "claim": "HVAC systems must still meet ventilation code requirements.",
                "source_id": "cdc_school",
                "role": "implementation_constraint",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "depends_on",
                "rationale": "Portable cleaner deployment depends on maintaining baseline HVAC ventilation.",
            }
        ],
    }
    source_lookup = {"epa_school": "EPA School Guidance", "cdc_school": "CDC School Guidance"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 95, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "Use portable cleaners as supplements.",
        "confidence": "medium",
        "evidence_roles": {
            "main_support": ["EPA School Guidance"],
            "conflicting_evidence": [],
            "scope_limits": [],
            "method_limits": ["CDC School Guidance"],
        },
        "audit_trail": [],
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup)

    assert repaired["evidence_roles"]["main_support"] != ["EPA School Guidance"]
    role_text = "\n".join(repaired["evidence_roles"]["scope_limits"] + repaired["evidence_roles"]["method_limits"])
    assert "HVAC systems must still meet ventilation code requirements" in role_text
    assert "Portable cleaner deployment depends on maintaining baseline HVAC ventilation" in "\n".join(
        repaired["audit_trail"]
    )


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
        "  'audit_trail': ['covid_c001']\n"
        "}))\n",
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
    )

    rendered = result.briefing_path.read_text(encoding="utf-8")
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "**Confidence:** medium" in rendered
    assert "flf_covid_case_brief" not in rendered
    assert "FLF COVID Case Brief" in rendered
    assert "The case turns on whether priors or likelihood updates explain the disagreement." in rendered
    assert summary["model_confidence"] == "high"
    assert summary["calibrated_confidence"] == "medium"


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
    assert "**Confidence:** low" in rendered
    assert "doc_a" not in rendered
    assert "Doc A" in rendered


def test_semantic_staged_brief_cli_runs_full_path(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
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
        "elif 'Prioritized map artifact:' in prompt:\n"
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
    assert "Demo Case Doc A" in rendered
    assert "demo_case_doc_a" not in rendered


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
