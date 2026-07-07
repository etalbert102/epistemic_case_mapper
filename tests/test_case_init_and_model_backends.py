from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from epistemic_case_mapper import cli
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION
from epistemic_case_mapper.staged_semantic_pipeline import (
    CLAIM_EXTRACTION_PROMPT_VERSION,
    RELATION_BATCH_PROMPT_VERSION,
    RELATION_PROMPT_VERSION,
    SourceChunk,
    SourceSpan,
    consolidate_claims_for_map,
    evaluate_staged_map_quality,
    _coverage_backfill_claims,
    _sharpen_relations,
)
from scripts import validate_submission_manifest, validate_submission_references, validate_worked_regions


def test_case_init_creates_runnable_package(monkeypatch, tmp_path: Path) -> None:
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
            "Demo Case",
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

    assert (tmp_path / "package.yaml").exists()
    assert (tmp_path / "data/cases/demo_case/case.yaml").exists()
    assert (tmp_path / "examples/demo_case/worked_map.json").exists()

    monkeypatch.setattr(
        validate_submission_manifest.sys,
        "argv",
        ["validate_submission_manifest.py", "--repo-root", str(tmp_path), "--manifest", "package.yaml"],
    )
    assert validate_submission_manifest.main() == 0
    monkeypatch.setattr(
        validate_worked_regions.sys,
        "argv",
        ["validate_worked_regions.py", "--repo-root", str(tmp_path), "--manifest", "package.yaml"],
    )
    assert validate_worked_regions.main() == 0
    monkeypatch.setattr(
        validate_submission_references.sys,
        "argv",
        ["validate_submission_references.py", "--repo-root", str(tmp_path), "--manifest", "package.yaml"],
    )
    assert validate_submission_references.main() == 0

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
            "run",
            "map",
            "--region",
            "demo_case_initial_region",
        ],
    )
    assert cli.main() == 0
    prompt_path = tmp_path / "prompts/demo_case_initial_region/map_prompt.txt"
    assert prompt_path.exists()
    assert MAP_PROMPT_VERSION in prompt_path.read_text(encoding="utf-8")


def test_semantic_run_uses_command_backend_and_validates(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "fake_model.py"
    fake_model.write_text(
        "import json\n"
        "print('Thinking...')\n"
        "print('```json')\n"
        "print(json.dumps({\n"
        "  'title': 'Generated Demo Map',\n"
        "  'status': 'human-review-needed',\n"
        f"  'prompt_procedure': {MAP_PROMPT_VERSION!r},\n"
        "  'evidence_mode': 'source_grounded',\n"
        "  'sources': ['demo_case_doc_a', 'demo_case_doc_b'],\n"
        "  'claims': [\n"
        "    {'claim_id': 'demo_case_c101', 'claim': 'Alpha supports a generated claim.', 'source_id': 'demo_case_doc_a', 'source_span': 'lines 1-1', 'excerpt': 'Alpha line.', 'entailed_by_excerpt': 'yes', 'role': 'conclusion_support'},\n"
        "    {'claim_id': 'demo_case_c102', 'claim': 'Gamma supplies a crux candidate.', 'sourcecap_id': 'demo_case_doc_b', 'source_span': 'lines 1-1', 'excerpt': 'Gamma line.', 'entailed_by__excerpt': 'yes', 'role': 'crux'}\n"
        "  ],\n"
        "  'relations': [{'relation_id': 'demo_case_r101', 'source_claim': 'demo_case_c102', 'target_claim': 'demo_case_c101', 'relation_type': 'crux_for', 'ration_type': 'The second claim affects how the first should be read.'}],\n"
        "  'crux_candidates': ['demo_case_c102 changes the interpretation of demo_case_c101.'],\n"
        "  'similar_but_not_identical': ['The two claims are related but distinct.'],\n"
        "  'evidence_check': [['Source grounding', 'Survives', 'Exact excerpts are present.']]\n"
        "}))\n"
        "print('```')\n",
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
            "run",
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
        ],
    )
    assert cli.main() == 0
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert generated["prompt_procedure"] == MAP_PROMPT_VERSION
    assert generated["claims"][1]["source_id"] == "demo_case_doc_b"
    assert generated["claims"][1]["entailed_by_excerpt"] == "yes"
    assert generated["relations"][0]["relation_type"] == "crux_for"
    assert generated["relations"][0]["rationale"].startswith("The second claim")


def test_prompt_backend_returns_prompt_text() -> None:
    result = run_model_backend("source bounded prompt", "prompt")
    assert result.prompt_only is True
    assert result.text == "source bounded prompt"


def test_command_backend_timeout_is_bounded() -> None:
    with pytest.raises(RuntimeError, match="timed out"):
        run_model_backend(
            "prompt",
            f"command:{sys.executable} -c 'import time; time.sleep(2)'",
            timeout_seconds=1,
        )


def test_command_backend_retries_transient_failure(tmp_path: Path) -> None:
    state_path = tmp_path / "attempts.txt"
    fake_model = tmp_path / "flaky_model.py"
    fake_model.write_text(
        "import pathlib, sys\n"
        f"path = pathlib.Path({str(state_path)!r})\n"
        "count = int(path.read_text() or '0') if path.exists() else 0\n"
        "path.write_text(str(count + 1))\n"
        "sys.stdin.read()\n"
        "if count == 0:\n"
        "    print('temporary failure', file=sys.stderr)\n"
        "    sys.exit(7)\n"
        "print('{\"ok\": true}')\n",
        encoding="utf-8",
    )

    result = run_model_backend(
        "prompt",
        f"command:{sys.executable} {fake_model}",
        timeout_seconds=5,
        max_retries=1,
    )

    assert result.text.strip() == '{"ok": true}'
    assert result.attempts == 2


def test_ollama_http_backend_sends_response_schema(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"message": {"content": "{\\"ok\\": true}"}}'

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    monkeypatch.setattr("epistemic_case_mapper.model_backends.request.urlopen", fake_urlopen)

    result = run_model_backend("prompt", "ollama:test-model", timeout_seconds=7, response_schema=schema)

    assert result.text == '{"ok": true}'
    assert captured["timeout"] == 7
    assert captured["payload"]["format"] == schema


def test_staged_semantic_map_assigns_ids_and_rejects_bad_chunk_claims(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "fake_staged_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    if 'Source ID: demo_case_doc_a' in prompt:\n"
        "        payload = {'claims': [\n"
        "            {'claim': 'Alpha supports a staged claim.', 'span_id': 'demo_case_doc_a_s0001', 'excerpt_entailed_by_excerpt': 'yes', 'role': 'conclusion_support'},\n"
        "            {'claim': 'Wrong span should be rejected.', 'span_id': 'missing_span', 'entailed_by_excerpt': 'yes', 'role': 'background'}\n"
        "        ]}\n"
        "    else:\n"
        "        payload = {'claims': [\n"
        "            {'claim': 'Gamma supplies a staged crux.', 'span_id': 'demo_case_doc_b_s0001', 'entailed_by_excerpt': 'yes', 'role': 'crux'}\n"
        "        ]}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {'pair_id': 'pair_001', 'source_claim': 'demo_case_c002', 'target_claim': 'demo_case_c001', 'relation_type': 'crux_for', 'rationale': 'The Gamma claim changes how the Alpha claim should be read.', 'crux_candidates': ['demo_case_c002 is a crux for demo_case_c001.'], 'similar_but_not_identical': []}\n"
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
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
        ],
    )
    assert cli.main() == 0
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert [claim["claim_id"] for claim in generated["claims"]] == ["demo_case_c001", "demo_case_c002"]
    assert generated["claims"][0]["excerpt"] == "Alpha line."
    assert generated["relations"][0]["relation_id"] == "demo_case_r001"
    assert generated["relations"][0]["source_claim"] == "demo_case_c002"
    assert generated["relations"][0]["relation_confidence"] == "medium"
    assert generated["relations"][0]["relation_provenance"] == "model_classified"
    assert generated["relations"][0]["relation_contract"]["source_anchor_a"] == "Alpha line."
    assert generated["relations"][0]["relation_contract"]["failure_condition"]
    assert "crux" in generated["relations"][0]["candidate_pair"]["reason"]
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["rejected_claims"][0]["reason"] == "unknown_span_id"
    assert summary["rejected_relations"] == []
    assert summary["quality_status"] in {"usable_with_review", "review_recommended", "needs_repair"}
    assert summary["quality_repair_prompt"] == "artifacts/semantic/demo_case_initial_region/staged/map_quality_repair_prompt.txt"
    quality_report = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/map_quality_report.json").read_text(encoding="utf-8"))
    assert quality_report["schema_id"] == "staged_map_quality_report_v1"
    assert quality_report["source_claim_counts"] == {"demo_case_doc_a": 1, "demo_case_doc_b": 1}
    assert "conclusion_support" in quality_report["claim_role_counts"]
    assert quality_report["summary"]["relation_contract_count"] == 1
    assert quality_report["relation_confidence_counts"]["medium"] == 1
    assert quality_report["scaffold"]["required_sources"] == ["demo_case_doc_a", "demo_case_doc_b"]
    claim_prompt = (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/claim_chunks/demo_case_doc_a_lines_1_2_prompt.txt").read_text(encoding="utf-8")
    assert "# Output Schema" in claim_prompt
    assert "# Examples" in claim_prompt
    assert "<source_span_catalog>" in claim_prompt
    assert "Deterministic map-quality scaffold" in claim_prompt
    assert "target_claim_roles" in claim_prompt
    relation_prompt = (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/relation_pairs/pair_001_prompt.txt").read_text(encoding="utf-8")
    assert "# Output Schema" in relation_prompt
    assert "# Examples" in relation_prompt
    assert "<deterministic_map_quality_scaffold>" in relation_prompt
    assert "Deterministic map-quality scaffold" in relation_prompt
    assert "relation_goals" in relation_prompt
    assert "relation evidence contract" in relation_prompt
    repair_prompt = (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/map_quality_repair_prompt.txt").read_text(encoding="utf-8")
    assert "Deterministic quality report" in repair_prompt
    assert "Candidate map:" in repair_prompt


def test_staged_semantic_map_uses_fallbacks_after_backend_errors(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "fallback_staged_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt and 'Source ID: demo_case_doc_a' in prompt:\n"
        "    print('backend failed', file=sys.stderr)\n"
        "    sys.exit(9)\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {'claims': [\n"
        "        {'claim': 'Gamma supplies a staged crux.', 'span_id': 'demo_case_doc_b_s0001', 'entailed_by_excerpt': 'yes', 'role': 'crux'}\n"
        "    ]}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {'pair_id': 'pair_001', 'source_claim': None, 'target_claim': None, 'relation_type': 'none', 'rationale': 'No edge.', 'crux_candidates': [], 'similar_but_not_identical': []}\n"
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
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--backend-retries",
            "0",
        ],
    )
    assert cli.main() == 0
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert generated["claims"][0]["extraction_method"] == "deterministic_fallback_span"
    assert generated["relations"][0]["extraction_method"] == "deterministic_fallback_pair"
    assert generated["relations"][0]["relation_confidence"] == "low"
    assert generated["relations"][0]["requires_review"] is True
    assert generated["relations"][0]["relation_contract"]["edge_basis"] == "role_template"
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["backend_retries"] == 0
    assert summary["rejected_claims"][0]["reason"] == "backend_error_used_deterministic_fallback"
    assert summary["rejected_relations"][-1]["reason"] == "model_under_related_used_deterministic_fallback"
    quality_report = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/map_quality_report.json").read_text(encoding="utf-8"))
    issue_types = {issue["issue_type"] for issue in quality_report["issues"]}
    assert "fallback_relation_needs_review" in issue_types


def test_staged_semantic_map_can_accept_quality_repair(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "quality_repair_model.py"
    fake_model.write_text(
        "import json, re, sys\n"
        "prompt = sys.stdin.read()\n"
        "if 'Deterministic quality report:' in prompt:\n"
        "    payload = {\n"
        "      'title': 'Repaired Demo Map',\n"
        "      'status': 'human-review-needed',\n"
        f"      'prompt_procedure': {MAP_PROMPT_VERSION!r},\n"
        "      'pipeline': 'staged_chunked_mapper_v1_quality_repaired',\n"
        "      'evidence_mode': 'source_grounded',\n"
        "      'sources': ['demo_case_doc_a', 'demo_case_doc_b'],\n"
        "      'claims': [\n"
        "        {'claim_id': 'demo_case_c001', 'claim': 'Alpha supports the initialized package question.', 'source_id': 'demo_case_doc_a', 'source_span': 'lines 1-1', 'excerpt': 'Alpha line.', 'entailed_by_excerpt': 'yes', 'role': 'conclusion_support'},\n"
        "        {'claim_id': 'demo_case_c002', 'claim': 'Gamma supplies a crux for the initialized package question.', 'source_id': 'demo_case_doc_b', 'source_span': 'lines 1-1', 'excerpt': 'Gamma line.', 'entailed_by_excerpt': 'yes', 'role': 'crux'},\n"
        "        {'claim_id': 'demo_case_c003', 'claim': 'Delta is a scope limit for the initialized package question.', 'source_id': 'demo_case_doc_b', 'source_span': 'lines 2-2', 'excerpt': 'Delta line.', 'entailed_by_excerpt': 'yes', 'role': 'scope_limit'}\n"
        "      ],\n"
        "      'relations': [\n"
        "        {'relation_id': 'demo_case_r001', 'source_claim': 'demo_case_c002', 'target_claim': 'demo_case_c001', 'relation_type': 'crux_for', 'rationale': 'The Gamma claim changes how the Alpha claim should be read.'},\n"
        "        {'relation_id': 'demo_case_r002', 'source_claim': 'demo_case_c003', 'target_claim': 'demo_case_c001', 'relation_type': 'refines', 'rationale': 'The Delta claim bounds the Alpha claim.'}\n"
        "      ],\n"
        "      'crux_candidates': ['demo_case_c002 is a crux for demo_case_c001.'],\n"
        "      'similar_but_not_identical': ['demo_case_c002 and demo_case_c003 play different roles.'],\n"
        "      'evidence_check': [['Source grounding', 'Survives', 'Exact excerpts are present.']]\n"
        "    }\n"
        f"elif {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    span_id = re.search(r'span_id: ([^\\n]+)', prompt).group(1)\n"
        "    payload = {'claims': [{'claim': 'Alpha supports an initial under-covered map.', 'span_id': span_id, 'entailed_by_excerpt': 'yes', 'role': 'conclusion_support'}]}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {}\n"
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
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--max-total-chunks",
            "1",
            "--repair-quality",
        ],
    )
    assert cli.main() == 0
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert generated["title"] == "Repaired Demo Map"
    assert len(generated["claims"]) == 3
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["llm_claim_count"] == 1
    assert summary["coverage_claim_count"] == 0
    assert summary["coverage_backfill"]["deterministic_claim_insertion"] == "disabled"
    assert summary["coverage_backfill"]["suppressed_candidate_count"] == 1
    assert summary["pre_consolidation_claim_count"] == 1
    assert summary["claim_count"] == 3
    assert summary["quality_repair"]["ran"] is True
    assert summary["quality_repair"]["accepted"] is True
    assert summary["quality_repair"]["reason"] == "accepted"
    assert summary["quality_repair"]["repaired_score"] >= summary["quality_repair"]["initial_score"]
    assert (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/map_quality_repair_raw.txt").exists()
    assert (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/map_quality_repaired_report.json").exists()


def test_staged_semantic_map_records_chunk_budget(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "budget_staged_model.py"
    fake_model.write_text(
        "import json, re, sys\n"
        "prompt = sys.stdin.read()\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    span_id = re.search(r'span_id: ([^\\n]+)', prompt).group(1)\n"
        "    payload = {'claims': [{'claim': 'Budgeted staged claim.', 'span_id': span_id, 'entailed_by_excerpt': 'yes', 'role': 'crux'}]}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    pair_id = re.search(r'Pair ID: ([^\\n]+)', prompt).group(1)\n"
        "    ids = re.findall(r'claim_id: ([^\\n]+)', prompt)\n"
        "    payload = {'pair_id': pair_id, 'source_claim': ids[0], 'target_claim': ids[1], 'relation_type': 'crux_for', 'rationale': 'The two budgeted chunks should be compared.', 'crux_candidates': ['budgeted crux'], 'similar_but_not_identical': []}\n"
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
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--chunk-lines",
            "1",
            "--chunk-overlap-lines",
            "0",
            "--max-total-chunks",
            "2",
        ],
    )
    assert cli.main() == 0
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["all_chunk_count"] == 4
    assert summary["selected_chunk_count"] == 2
    assert summary["skipped_chunk_count"] == 2
    assert summary["coverage_backfill"]["deterministic_claim_insertion"] == "disabled"
    assert summary["coverage_backfill"]["backfilled_claim_count"] == 0
    assert summary["coverage_backfill"]["suppressed_candidate_count"] == 2
    assert summary["coverage_claim_count"] == 0
    assert summary["pre_consolidation_claim_count"] == summary["llm_claim_count"]
    assert {chunk["source_id"] for chunk in summary["chunks"]} == {"demo_case_doc_a", "demo_case_doc_b"}
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert not any(str(claim.get("extraction_method", "")).startswith("deterministic") for claim in generated["claims"])
    assert (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/coverage_backfill_claims.json").exists()
    assert (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/claim_consolidation_report.json").exists()


def test_claim_consolidation_preserves_supporting_sources() -> None:
    claims = [
        {
            "claim_id": "demo_c001",
            "claim": "The intervention was not associated with worse cardiovascular outcomes.",
            "source_id": "doc_a",
            "source_span": "lines 1-1",
            "excerpt": "The intervention was not associated with worse cardiovascular outcomes.",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
        },
        {
            "claim_id": "demo_c002",
            "claim": "The intervention was not associated with worse cardiovascular outcomes in adults.",
            "source_id": "doc_b",
            "source_span": "lines 2-2",
            "excerpt": "The intervention was not associated with worse cardiovascular outcomes in adults.",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
        },
        {
            "claim_id": "demo_c003",
            "claim": "The intervention was associated with higher risk in a subgroup.",
            "source_id": "doc_c",
            "source_span": "lines 1-1",
            "excerpt": "The intervention was associated with higher risk in a subgroup.",
            "entailed_by_excerpt": "yes",
            "role": "conclusion_support",
        },
    ]

    consolidated, report = consolidate_claims_for_map(claims)

    assert report["changed"] is True
    assert len(consolidated) == 2
    merged = next(claim for claim in consolidated if claim["claim_id"] in {"demo_c001", "demo_c002"})
    assert set(merged["supporting_sources"]) == {"doc_a", "doc_b"}
    assert set(merged["supporting_claim_ids"]) == {"demo_c001", "demo_c002"}
    assert any(claim["claim_id"] == "demo_c003" for claim in consolidated)


def test_coverage_backfill_reports_warnings_without_adding_claims() -> None:
    span = SourceSpan(
        span_id="doc_s001",
        source_id="doc",
        source_span="lines 1-1",
        text="Substituting plant protein for egg protein reduced mortality risk in the cohort.",
    )
    chunk = SourceChunk(
        chunk_id="doc_chunk_001",
        source_id="doc",
        title="Doc",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="[doc_s001] Substituting plant protein for egg protein reduced mortality risk in the cohort.",
        plain_text=span.text,
        spans=(span,),
    )
    existing_claims = [
        {
            "claim_id": "demo_c001",
            "claim": "Generic replacement analyses matter for interpretation.",
            "source_id": "doc",
            "source_span": "lines 2-2",
            "excerpt": "Generic replacement analyses matter for interpretation.",
            "entailed_by_excerpt": "yes",
            "role": "implementation_constraint",
        }
    ]

    backfilled, report = _coverage_backfill_claims(
        all_chunks=[chunk],
        selected_chunks=[],
        existing_claims=existing_claims,
        id_prefix="demo",
    )

    assert backfilled == []
    assert report["deterministic_claim_insertion"] == "disabled"
    assert report["skipped_chunk_count"] == 1
    assert report["backfilled_claim_count"] == 0
    assert report["concept_gap_backfilled_claim_count"] == 0
    assert report["suppressed_candidate_count"] == 1
    assert "plant protein" in report["suppressed_candidates"][0]["excerpt"].lower()


def test_staged_semantic_map_batches_relation_pairs(monkeypatch, tmp_path: Path) -> None:
    _init_three_doc_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "batch_relation_model.py"
    fake_model.write_text(
        "import json, re, sys\n"
        "prompt = sys.stdin.read()\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    span_id = re.search(r'span_id: ([^\\n]+)', prompt).group(1)\n"
        "    payload = {'claims': [{'claim': 'Batched relation source claim.', 'span_id': span_id, 'entailed_by_excerpt': 'yes', 'role': 'crux'}]}\n"
        f"elif {RELATION_BATCH_PROMPT_VERSION!r} in prompt:\n"
        "    pairs = re.findall(r'Pair ID: (pair_[0-9]+)', prompt)\n"
        "    blocks = prompt.split('Pair ID: ')[1:]\n"
        "    relations = []\n"
        "    for pair_id, block in zip(pairs, blocks):\n"
        "        ids = re.findall(r'claim_id: ([^\\n]+)', block)\n"
        "        relations.append({'pair_id': pair_id, 'source_claim': ids[0], 'target_claim': ids[1], 'relation_type': 'crux_for', 'rationale': 'The batch classifies this pair.', 'crux_candidates': [pair_id + ' crux'], 'similar_but_not_identical': []})\n"
        "    payload = {'relations': relations}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {}\n"
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
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--max-relation-pairs",
            "2",
            "--relation-batch-size",
            "2",
        ],
    )
    assert cli.main() == 0
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert len(generated["relations"]) == 2
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["relation_batch_size"] == 2
    assert summary["relation_batch_count"] == 1
    assert (tmp_path / "artifacts/semantic/demo_case_initial_region/staged/relation_batches/batch_001_prompt.txt").exists()


def test_staged_map_quality_report_flags_missing_source_and_duplicates() -> None:
    class _Thresholds:
        min_claims = 3
        max_claims = 8
        min_relation_types = 2

    class _Region:
        required_sources = ["doc_a", "doc_b"]
        thresholds = _Thresholds()

    class _Ontology:
        def permitted_types(self) -> set[str]:
            return {"supports", "crux_for", "in_tension_with"}

    class _Manifest:
        relation_ontology = _Ontology()

    case_manifest = CaseManifest.model_validate(
        {
            "case_id": "demo",
            "title": "Demo",
            "question": "What matters?",
            "case_type": "test",
            "sources": [
                {"source_id": "doc_a", "title": "A", "text": "Alpha evidence."},
                {"source_id": "doc_b", "title": "B", "text": "Beta evidence."},
            ],
        }
    )
    candidate_map = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "Alpha evidence changes the decision.",
                "source_id": "doc_a",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "demo_c002",
                "claim": "Alpha evidence changes the decision substantially.",
                "source_id": "doc_a",
                "entailed_by_excerpt": "uncertain",
                "role": "conclusion_support",
            },
        ],
        "relations": [],
    }

    report = evaluate_staged_map_quality(
        manifest=_Manifest(),
        region=_Region(),
        case_manifest=case_manifest,
        all_chunks=[],
        selected_chunks=[],
        skipped_chunks=[],
        candidate_map=candidate_map,
        rejected_claims=[],
        rejected_relations=[],
    )

    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert report["status"] == "needs_repair"
    assert "missing_source_claim_coverage" in issue_types
    assert "missing_relations" in issue_types
    assert "near_duplicate_claims" in issue_types
    assert report["scaffold"]["source_roles"]["doc_a"]["display_title"] == "A"
    assert report["scaffold"]["source_roles"]["doc_a"]["inferred"] is True


def test_staged_map_quality_flags_weak_relation_rationales() -> None:
    class _Thresholds:
        min_claims = 2
        max_claims = 8
        min_relation_types = 1

    class _Region:
        required_sources = ["doc_a", "doc_b"]
        thresholds = _Thresholds()

    class _Ontology:
        def permitted_types(self) -> set[str]:
            return {"supports", "crux_for", "in_tension_with"}

    class _Manifest:
        relation_ontology = _Ontology()

    case_manifest = CaseManifest.model_validate(
        {
            "case_id": "demo",
            "title": "Demo",
            "question": "What matters?",
            "case_type": "test",
            "sources": [
                {"source_id": "doc_a", "title": "A", "text": "Alpha evidence."},
                {"source_id": "doc_b", "title": "B", "text": "Beta evidence."},
            ],
        }
    )
    candidate_map = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "Alpha evidence changes the decision.",
                "source_id": "doc_a",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "demo_c002",
                "claim": "Beta evidence is a crux.",
                "source_id": "doc_b",
                "entailed_by_excerpt": "yes",
                "role": "crux",
            },
        ],
        "relations": [
            {
                "relation_id": "demo_r001",
                "source_claim": "demo_c002",
                "target_claim": "demo_c001",
                "relation_type": "crux_for",
                "rationale": "They are related.",
            }
        ],
    }

    report = evaluate_staged_map_quality(
        manifest=_Manifest(),
        region=_Region(),
        case_manifest=case_manifest,
        all_chunks=[],
        selected_chunks=[],
        skipped_chunks=[],
        candidate_map=candidate_map,
        rejected_claims=[],
        rejected_relations=[],
    )

    issue_types = {issue["issue_type"] for issue in report["issues"]}
    assert "weak_relation_rationales" in issue_types


def test_relation_sharpening_preserves_model_relation_types() -> None:
    claims = [
        {
            "claim_id": "demo_c001",
            "claim": "Portable cleaners should be used as supplemental filtration.",
            "role": "crux",
        },
        {
            "claim_id": "demo_c002",
            "claim": "Measured PM reductions may not imply meaningful health benefits.",
            "role": "scope_limit",
        },
        {
            "claim_id": "demo_c003",
            "claim": "HVAC systems must still meet baseline ventilation requirements.",
            "role": "implementation_constraint",
        },
    ]
    relations = [
        {
            "relation_id": "demo_r001",
            "source_claim": "demo_c002",
            "target_claim": "demo_c001",
            "relation_type": "refines",
            "rationale": "The small PM reductions are unclear for health benefits and limit the support claim.",
        },
        {
            "relation_id": "demo_r002",
            "source_claim": "demo_c003",
            "target_claim": "demo_c001",
            "relation_type": "supports",
            "rationale": "Portable cleaner deployment only works if baseline HVAC ventilation is maintained.",
        },
    ]

    sharpened = _sharpen_relations(
        relations,
        claims,
        {"supports", "refines", "similar_to", "depends_on", "crux_for", "in_tension_with"},
    )

    assert sharpened == relations
    assert all("deterministic_sharpening" not in relation for relation in sharpened)


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


def _init_three_doc_case(monkeypatch, tmp_path: Path) -> None:
    doc_a = tmp_path / "doc_a.txt"
    doc_b = tmp_path / "doc_b.txt"
    doc_c = tmp_path / "doc_c.txt"
    doc_a.write_text("Alpha claim line.\n", encoding="utf-8")
    doc_b.write_text("Beta claim line.\n", encoding="utf-8")
    doc_c.write_text("Gamma claim line.\n", encoding="utf-8")
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
            "Can this package batch relation pairs?",
            "--docs",
            str(doc_a),
            str(doc_b),
            str(doc_c),
        ],
    )
    assert cli.main() == 0
