from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from epistemic_case_mapper import cli
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION
from epistemic_case_mapper.staged_semantic_pipeline import (
    CLAIM_EXTRACTION_PROMPT_VERSION,
    RELATION_BATCH_PROMPT_VERSION,
    RELATION_PROMPT_VERSION,
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
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["rejected_claims"][0]["reason"] == "unknown_span_id"
    assert summary["rejected_relations"] == []


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
    summary = json.loads((tmp_path / "artifacts/semantic/demo_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8"))
    assert summary["backend_retries"] == 0
    assert summary["rejected_claims"][0]["reason"] == "backend_error_used_deterministic_fallback"
    assert summary["rejected_relations"][-1]["reason"] == "model_under_related_used_deterministic_fallback"


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
    assert {chunk["source_id"] for chunk in summary["chunks"]} == {"demo_case_doc_a", "demo_case_doc_b"}


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
