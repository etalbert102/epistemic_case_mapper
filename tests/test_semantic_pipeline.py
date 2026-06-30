from __future__ import annotations

import json
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.semantic_pipeline import (
    CRITIQUE_PROMPT_VERSION,
    MAP_PROMPT_VERSION,
    build_critique_prompt,
    build_map_prompt,
    validate_critique_candidate,
    validate_map_candidate,
)
from test_submission_manifest_generalization import _write_transfer_fixture


def test_semantic_prompt_builders_are_source_bounded(tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)

    prompt = build_map_prompt(tmp_path, "submission_manifest.yaml", "demo_region_json")

    assert MAP_PROMPT_VERSION in prompt
    assert "source_id: demo_source_1" in prompt
    assert "1: Alpha line." in prompt
    assert "Return only JSON" in prompt
    assert "Allowed relation types" in prompt

    critique_prompt = build_critique_prompt(tmp_path, "submission_manifest.yaml", "demo_region_json")
    assert CRITIQUE_PROMPT_VERSION in critique_prompt
    assert "Candidate map:" in critique_prompt
    assert "Flat baseline:" in critique_prompt


def test_semantic_map_and_critique_validation(tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    candidate_path = tmp_path / "candidate_map.json"
    candidate_path.write_text(json.dumps(_candidate_map(), indent=2), encoding="utf-8")

    assert validate_map_candidate(tmp_path, "submission_manifest.yaml", "demo_region_json", candidate_path) == []

    broken_path = tmp_path / "broken_map.json"
    broken = _candidate_map()
    broken["relations"][0]["relation_type"] = "undefined_custom_relation"
    broken_path.write_text(json.dumps(broken, indent=2), encoding="utf-8")
    assert any(
        "semantic_map_relation_unknown_type" in failure
        for failure in validate_map_candidate(tmp_path, "submission_manifest.yaml", "demo_region_json", broken_path)
    )

    critique_path = tmp_path / "critique.json"
    critique_path.write_text(json.dumps(_candidate_critique(), indent=2), encoding="utf-8")
    assert validate_critique_candidate(critique_path) == []


def test_semantic_cli_validates_candidate(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    candidate_path = tmp_path / "candidate_map.json"
    candidate_path.write_text(json.dumps(_candidate_map(), indent=2), encoding="utf-8")

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "semantic",
            "validate",
            "map",
            "--region",
            "demo_region_json",
            "--path",
            str(candidate_path),
        ],
    )

    assert cli.main() == 0


def _candidate_map() -> dict:
    return {
        "title": "Demo Candidate Map",
        "status": "human-review-needed",
        "prompt_procedure": MAP_PROMPT_VERSION,
        "evidence_mode": "source_grounded",
        "sources": ["demo_source_1", "demo_source_2"],
        "claims": [
            {
                "claim_id": "claim:demo:301",
                "claim": "Alpha supports a semantic candidate claim.",
                "source_id": "demo_source_1",
                "source_span": "lines 1-1",
                "excerpt": "Alpha line.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "claim:demo:302",
                "claim": "Gamma supports a crux candidate.",
                "source_id": "demo_source_2",
                "source_span": "lines 1-1",
                "excerpt": "Gamma line.",
                "entailed_by_excerpt": "yes",
                "role": "crux",
            },
            {
                "claim_id": "claim:demo:303",
                "claim": "Beta supports another candidate claim.",
                "source_id": "demo_source_1",
                "source_span": "lines 2-2",
                "excerpt": "Beta line.",
                "entailed_by_excerpt": "yes",
                "role": "background",
            },
        ],
        "relations": [
            {
                "relation_id": "rel:demo:301",
                "source_claim": "claim:demo:302",
                "target_claim": "claim:demo:301",
                "relation_type": "crux_for",
                "rationale": "The crux claim affects the conclusion-supporting claim.",
            },
            {
                "relation_id": "rel:demo:302",
                "source_claim": "claim:demo:303",
                "target_claim": "claim:demo:301",
                "relation_type": "supports",
                "rationale": "The second source-one claim supports the conclusion-supporting claim.",
            },
        ],
        "crux_candidates": ["claim:demo:302 changes how claim:demo:301 should be read."],
        "similar_but_not_identical": ["claim:demo:301 and claim:demo:303 are related but distinct."],
        "evidence_check": [["Source grounding", "Survives", "Exact excerpts are present."], ["Crux", "Survives", "A claim ID is named."]],
    }


def _candidate_critique() -> dict:
    return {
        "title": "Demo Candidate Critique",
        "status": "human-review-needed",
        "prompt_procedure": CRITIQUE_PROMPT_VERSION,
        "findings": [
            {
                "finding_id": "critique_001",
                "severity": "risk",
                "category": "baseline_uplift",
                "target_id": "overall",
                "issue": "The map may be only mildly better than the baseline.",
                "source_basis": "baseline and candidate map comparison",
                "recommended_fix": "Add a sharper crux or record the mild uplift.",
            }
        ],
    }
